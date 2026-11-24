"""Small correctness and interrupted-run checks; no frozen main experiment."""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "graph_runtime"))
import exact_label_correcting as lc
from src.round5.exact_enumeration import exact_enumeration


def case(branches, *, supports=None, source=0, target=3, **config):
    nodes = sorted({source, target} | {v for u, v, r in branches} | {u for u, v, r in branches})
    return {
        "case": "small_lc_unit_case", "directed": True, "nodes": nodes,
        "source": source, "target": target,
        "branches": [dict(source=u, target=v, r_pu=r, x_pu=0.0, rate_pu=None)
                     for u, v, r in branches],
        "supports": supports or {},
        "config": {"p_transfer_pu": 0.1, "q_transfer_pu": 0.0,
                   "voltage_lower_bound": 0.5, **config},
    }


class ExactLabelCorrectingTests(unittest.TestCase):
    def assert_matches_oracle(self, data):
        graph, source, target, specs, cfg = lc.load_case_dict(data)
        oracle = exact_enumeration(graph, source, target, specs, cfg,
                                   max_depth=len(graph.nodes))
        actual = lc.run(data)
        self.assertTrue(actual["status"].startswith("COMPLETED"), actual)
        self.assertTrue(actual["exact_certified"])
        self.assertEqual(actual["feasible"], oracle.feasible)
        if oracle.feasible:
            self.assertAlmostEqual(actual["common_evaluation"]["objective"],
                                   oracle.objective, places=11)
        return actual

    def test_fifo_does_not_stop_at_first_goal(self):
        data = case([(0, 3, 0.8), (0, 1, 0.1), (1, 2, 0.1), (2, 3, 0.1)])
        result = self.assert_matches_oracle(data)
        self.assertEqual(result["path"], [0, 1, 2, 3])
        self.assertGreater(result["stats"]["labels_expanded"], 1)

    def test_disconnected_exhaustion_proves_infeasible(self):
        result = self.assert_matches_oracle(case([(0, 1, 0.1)]))
        self.assertEqual(result["status"], "COMPLETED_INFEASIBLE")

    def test_support_saturation_and_cost_match_oracle(self):
        support = {"1": {"capacity_pu": 0.3, "fixed_cost": 0.002, "unit_cost": 0.01},
                   "2": {"capacity_pu": 0.1, "fixed_cost": 0.001, "unit_cost": 0.02}}
        data = case([(0, 1, 2.0), (0, 2, 0.1), (2, 1, 0.1), (1, 3, 1.8),
                     (2, 3, 2.4)], supports=support, voltage_lower_bound=0.8,
                    max_support_nodes=1, lambda_support_count=0.001)
        self.assert_matches_oracle(data)

    def test_endpoint_support_policy_and_trivial_path(self):
        data = case([(0, 3, 2.0)], supports={"3": {"capacity_pu": 0.2, "fixed_cost": 0.0}},
                    voltage_lower_bound=0.9, allow_support_at_target=False)
        self.assertFalse(self.assert_matches_oracle(data)["feasible"])
        data["config"]["allow_support_at_target"] = True
        self.assertTrue(self.assert_matches_oracle(data)["feasible"])
        trivial = self.assert_matches_oracle(case([], source=0, target=0))
        self.assertEqual(trivial["path"], [0])

    def test_historical_counterexample_matches_oracle(self):
        from src.round5.test_cases import dominance_counterexample_case
        name, graph, source, target, specs, cfg = dominance_counterexample_case()
        data = {"case": name, "nodes": sorted(graph.nodes), "source": source, "target": target,
                "branches": [asdict(b) for edges in graph.adjacency.values() for b in edges],
                "supports": {str(n): asdict(s) for n, s in specs.items()}, "config": asdict(cfg)}
        self.assert_matches_oracle(data)

    def test_no_oracle_or_previous_search_call(self):
        import joint_search
        import src.round5.vamls as old_labels
        with patch.object(joint_search, "search", side_effect=AssertionError("old search called")), \
             patch.object(joint_search, "run", side_effect=AssertionError("old run called")), \
             patch.object(old_labels, "dominates", side_effect=AssertionError("old dominance called")), \
             patch.object(joint_search, "dominates", side_effect=AssertionError("old dominance called")):
            result = lc.run(case([(0, 3, 0.2), (0, 1, 0.1), (1, 3, 0.1)]))
        self.assertTrue(result["exact_certified"])

    def test_zero_time_and_limits_are_unknown_without_witness(self):
        data = case([(0, 1, 0.1), (1, 3, 0.1)])
        for kwargs, expected in [({"timeout_seconds": 0}, "TIMEOUT"),
                                 ({"max_labels": 1}, "RESOURCE_LIMIT"),
                                 ({"max_resident": 1}, "RESOURCE_LIMIT")]:
            with self.subTest(kwargs=kwargs):
                result = lc.run(data, **kwargs)
                self.assertEqual(result["status"], expected)
                self.assertIsNone(result["feasible"])
                self.assertIsNone(result["common_evaluation"]["feasible"])
                self.assertFalse(result["exact_certified"])

    def test_resource_limit_retains_validated_incumbent(self):
        data = case([(0, 3, 0.8), (0, 1, 0.1), (1, 3, 0.1)])
        result = lc.run(data, max_expansions=1)
        self.assertEqual(result["status"], "RESOURCE_LIMIT")
        self.assertTrue(result["feasible"])
        self.assertEqual(result["path"], [0, 3])
        self.assertFalse(result["exact_certified"])
        self.assertEqual(result["stats"]["labels_expanded"], 1)

    def test_timeout_during_evaluation_retains_validated_incumbent(self):
        data = case([(0, 3, 0.8), (0, 1, 0.1), (1, 3, 0.1)])
        tick = [0.0]
        original_evaluate = lc.common_evaluate

        def evaluated_then_deadline(*args):
            result = original_evaluate(*args)
            if args[1]:
                tick[0] = 2.0
            return result

        with patch.object(lc.time, "perf_counter", side_effect=lambda: tick[0]), \
             patch.object(lc, "common_evaluate", side_effect=evaluated_then_deadline):
            result = lc.run(data, timeout_seconds=1.0)
        self.assertEqual(result["status"], "TIMEOUT")
        self.assertTrue(result["feasible"])
        self.assertEqual(result["path"], [0, 3])
        self.assertFalse(result["exact_certified"])

    def test_exception_retains_validated_incumbent(self):
        data = case([(0, 3, 0.8), (0, 1, 0.1), (1, 3, 0.1)])
        original_branch = lc.evaluate_branch_pu

        def break_second_branch(branch, *args):
            if branch.target == 1:
                raise ArithmeticError("injected branch failure")
            return original_branch(branch, *args)

        with patch.object(lc, "evaluate_branch_pu", side_effect=break_second_branch):
            result = lc.run(data)
        self.assertEqual(result["status"], "ERROR")
        self.assertTrue(result["feasible"])
        self.assertFalse(result["exact_certified"])
        self.assertIn("injected branch failure", result["error_message"])

    def test_preserves_input_and_rejects_unsupported_domain(self):
        data = case([(0, 3, 0.1)])
        original = deepcopy(data)
        lc.run(data)
        self.assertEqual(data, original)
        data["config"]["q_transfer_pu"] = -0.01
        with self.assertRaises(ValueError):
            lc.run(data)


if __name__ == "__main__":
    unittest.main()
