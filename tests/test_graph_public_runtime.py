"""Public-harness checks: state reporting, oracle identity and retained adverse evidence."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).absolute().parents[1] / "src"))
from graph_runtime import api


class PublicRuntimeTests(unittest.TestCase):
    def test_interrupted_without_witness_remains_unknown(self):
        data, _ = api.load_case("REVIEWER_SYNTHETIC_GRAPH")
        oracle = api.frozen_oracles()[data["case"]]
        result = {"status": "TIMEOUT", "feasible": None, "path": [], "support_nodes": [],
                  "exact_certified": False, "common_evaluation": {"objective": None}}
        checked = api.check_result(data, result, oracle)
        self.assertTrue(checked["check_passed"])
        self.assertEqual(checked["outcome"], "UNKNOWN_AFTER_LIMIT")
        self.assertIsNone(checked["optimality_gap_percent"])

    def test_false_infeasibility_and_interrupted_certificate_are_rejected(self):
        data, _ = api.load_case("REVIEWER_SYNTHETIC_GRAPH")
        oracle = api.frozen_oracles()[data["case"]]
        result = {"status": "COMPLETED_INFEASIBLE", "feasible": False, "path": [], "support_nodes": [],
                  "exact_certified": True, "common_evaluation": {"objective": None}}
        self.assertFalse(api.check_result(data, result, oracle)["check_passed"])
        result["status"] = "RESOURCE_LIMIT"
        self.assertTrue(any("interrupted" in message for message in api.check_result(data, result, oracle)["issues"]))

    def test_real_fixed_cap_adapter_preserves_budget_status(self):
        data, _ = api.load_case("REVIEWER_SYNTHETIC_GRAPH")
        original = deepcopy(data)
        budgets = {**api.settings()["budgets"], "max_labels": 1}
        result = api.run_method(data, "cap_3", budgets)
        self.assertEqual(result["status"], "RESOURCE_LIMIT")
        self.assertIsNone(result["feasible"])
        self.assertFalse(result["exact_certified"])
        self.assertEqual(data, original)

    def test_saved_adverse_case_remains_suboptimal_and_uncertified(self):
        saved = api.read_json("benchmarks/graph/adversarial_13_reference.json")
        data, _ = api.load_case(saved["case"]["case"])
        self.assertEqual(len(data["nodes"]), 13)
        checked = api.check_result(data, saved["adaptive_result"], api.frozen_oracles()[data["case"]])
        self.assertTrue(checked["check_passed"], checked["issues"])
        self.assertEqual(checked["outcome"], "SUBOPTIMAL_UNCERTIFIED_WITNESS")
        self.assertAlmostEqual(checked["optimality_gap_percent"], 1.0854210781654738, places=10)


if __name__ == "__main__":
    unittest.main()
