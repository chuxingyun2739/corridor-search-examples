"""Meaningful boundary checks for genuine CH and weighted directed PLL code."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).absolute().parents[1] / "src"))
from static_engines import BudgetExceeded, CHIndex, GraphMismatch, HubLabelIndex
from graph_runtime.static_checks import check_engine


class StaticEngineTests(unittest.TestCase):
    def test_all_pairs_parallel_arcs_zero_cycle_directed_and_disconnected(self):
        nodes = list(range(7))
        edges = [(0, 1, 2.0), (0, 1, 1.0), (1, 2, 0.0), (2, 1, 0.0),
                 (2, 3, 2.0), (0, 3, 9.0), (3, 4, 1.0), (4, 2, 4.0), (5, 0, 3.0)]
        for engine in (CHIndex, HubLabelIndex):
            with self.subTest(engine=engine.__name__):
                result = check_engine(engine, edges, nodes)
                self.assertEqual(result["validation_status"], "PASS", result["issues"])
                self.assertEqual(result["query_count"], 49)
                self.assertTrue(any(not row["reachable"] for row in result["queries"]))

    def test_ch_nested_shortcut_unpacks_original_edges(self):
        edges = [(0, 1, 1.0), (1, 2, 1.0), (2, 3, 1.0), (0, 3, 9.0)]
        index = CHIndex.build(edges, [0, 1, 2, 3], order=[1, 2, 0, 3])
        answer = index.query(0, 3)
        self.assertGreaterEqual(index.stats["shortcuts_added"], 2)
        self.assertGreaterEqual(index.stats["max_shortcut_depth"], 2)
        self.assertEqual(answer["path"], [0, 1, 2, 3])
        self.assertEqual(answer["edge_ids"], [0, 1, 2])
        self.assertEqual(answer["distance"], 3.0)

    def test_hl_query_uses_preprocessed_two_hop_labels(self):
        edges = [(u, v, 1.0) for u, v in [(0, 1), (1, 0), (1, 2), (2, 1), (2, 3), (3, 2)]]
        index = HubLabelIndex.build(edges, [0, 1, 2, 3], order=[1, 2, 0, 3])
        self.assertGreater(index.stats["pruned_vertices"], 0)
        self.assertGreater(index.stats["total_label_entries"], 0)
        with patch.object(index, "_pruned_dijkstra", side_effect=AssertionError("query started new search")):
            self.assertEqual(index.label_distance(0, 3), 3.0)
            self.assertEqual(index.query(0, 3)["path"], [0, 1, 2, 3])

    def test_graph_identity_rejects_weight_change_and_wrong_hash(self):
        for engine in (CHIndex, HubLabelIndex):
            with self.subTest(engine=engine.__name__):
                index = engine.build([(0, 1, 1.0)], [0, 1])
                with self.assertRaises(GraphMismatch):
                    index.assert_compatible([(0, 1, 2.0)], [0, 1])
                with self.assertRaises(GraphMismatch):
                    index.query(0, 1, expected_graph_hash="wrong-instance")

    def test_zero_budgets_report_limits_not_unreachability(self):
        for engine in (CHIndex, HubLabelIndex):
            with self.subTest(engine=engine.__name__):
                with self.assertRaises(BudgetExceeded) as zero_time:
                    engine.build([(0, 1, 1.0)], [0, 1], preprocessing_timeout_s=0)
                self.assertEqual(zero_time.exception.status, "TIMEOUT")
                with self.assertRaises(BudgetExceeded) as zero_memory:
                    engine.build([(0, 1, 1.0)], [0, 1], memory_cap_mb=0)
                self.assertEqual(zero_memory.exception.status, "RESOURCE_LIMIT")
                index = engine.build([(0, 1, 1.0)], [0, 1])
                with self.assertRaises(BudgetExceeded) as query_time:
                    index.query(0, 1, query_timeout_s=0)
                self.assertEqual(query_time.exception.status, "TIMEOUT")


if __name__ == "__main__":
    unittest.main()
