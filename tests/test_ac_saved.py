"""Saved-evidence checks and deliberate in-memory corruption controls.

No fixture on disk is modified and no scientific solver is called.
"""
import copy
import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).absolute().parents[1] / "scripts/verify_ac_saved.py"
SPEC = importlib.util.spec_from_file_location("verify_ac_saved", SCRIPT)
AC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AC)


class SavedACEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = AC.load_bundle()

    def check_corruption(self, mutate, expected_check):
        bundle = copy.deepcopy(self.original)
        mutate(bundle)
        result = AC.verify_bundle(bundle)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any(x["check"] == expected_check for x in result["failures"]), result["failures"])

    def test_original_saved_evidence(self):
        result = AC.verify_bundle(self.original)
        self.assertEqual(result["status"], "PASS", result["failures"])
        self.assertEqual(result["files_sha256_checked"], 20)
        self.assertEqual(result["observed"]["method_records"], 5)
        self.assertEqual(result["observed"]["selected_certificates"], 4)
        self.assertEqual(result["observed"]["candidate_mappings"], 26)
        self.assertFalse(result["L6_supported"])

    def test_resource_limit_with_and_without_certificate(self):
        limited = [r for r in self.original["records"] if r["method_result"]["status"] == "RESOURCE_LIMIT"]
        self.assertEqual(sorted(r["method_result"]["certified"] for r in limited), [False, True])
        absent = next(r for r in limited if not r["method_result"]["certified"])
        self.assertIsNone(absent["method_result"]["metrics"])
        self.assertIsNone(absent["certificate"])

    def test_graph_actions_are_not_AC_Mvar_controls(self):
        result = AC.verify_bundle(self.original)
        sample = next(r for r in result["saved_values"] if r["id"].startswith("ieee57_L110")
                      and r["id"].endswith("DVR_MLS_PORTFOLIO_V2_ANCHOR"))
        self.assertEqual(sample["graph_support_nodes"], [23, 25])
        self.assertEqual(sample["AC_hosts"], [14, 38, 47])
        self.assertFalse(sample["graph_support_equals_AC_hosts"])

    def test_context_identity_corruption(self):
        self.check_corruption(lambda b: b["records"][0]["context"].update(model_hash="0" * 64), "model_identity_metadata")

    def test_PF_flag_corruption(self):
        self.check_corruption(lambda b: b["records"][0]["certificate"].update(PF_converged=False), "saved_acceptance_flags")

    def test_Q_bound_corruption(self):
        def mutate(b):
            b["records"][0]["status_controls"]["controls"]["Q_support_mvar"][0] = 50.0
        self.check_corruption(mutate, "support_Q_bounds")

    def test_Pg_command_corruption(self):
        def mutate(b):
            b["records"][0]["status_controls"]["controls"]["generation"][0]["P_mw"] += 1.0
        self.check_corruption(mutate, "generation_command:ext_grid:0")

    def test_voltage_vector_corruption(self):
        def mutate(b):
            b["records"][0]["certificate"]["metrics"]["vm_by_bus"]["0"] += 0.1
        self.check_corruption(mutate, "reaggregated_metric:voltage_RMS_deviation")

    def test_optimizer_objective_corruption(self):
        def mutate(b):
            b["records"][0]["status_controls"]["objective"] += 1.0
        self.check_corruption(mutate, "saved_loss_objective")

    def test_missing_metrics_cannot_be_filled_with_zero(self):
        def mutate(b):
            next(r for r in b["records"] if not r["method_result"]["certified"])["method_result"]["metrics"] = {"P_loss_AC_MW": 0.0}
        self.check_corruption(mutate, "uncertified_metrics_remain_missing")

    def test_graph_actions_cannot_replace_AC_host_mapping(self):
        def mutate(b):
            r = next(r for r in b["records"] if r["entry"]["id"] == "ieee57_L110_CAP20__demand__DVR_MLS_PORTFOLIO_V2_ANCHOR")
            r["method_result"]["candidates"][0]["hosts"] = [23, 25]
        self.check_corruption(mutate, "candidate_host_mapping:1")

    def test_summary_numeric_corruption(self):
        def mutate(b):
            b["summary"][0]["P_loss_AC_MW"] = "0.0"
        self.check_corruption(mutate, "reaggregated_metric:P_loss_AC_MW")

    def test_hash_integrity_rejects_changed_bytes(self):
        item = self.original["manifest"]["files"][0]
        raw = AC.checked_file(AC.DEFAULT_DATA, item["path"]).read_bytes()
        self.assertTrue(AC.hash_matches(raw, item))
        self.assertFalse(AC.hash_matches(raw + b" ", item))

    def test_external_paths_rejected_without_reading_them(self):
        for value in ("../outside.json", "/outside.json", "X:/outside.json", "//server/share/file.json"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                AC.relative_path(value)


if __name__ == "__main__":
    unittest.main()
