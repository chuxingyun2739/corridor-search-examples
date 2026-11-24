"""Run explicitly limited smoke, representative correctness, or cap checks."""
import argparse
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).absolute().parents[1] / "src"))
from graph_runtime import api


def run_mode(mode):
    config = api.settings()
    chosen = config["modes"][mode]
    oracle = api.frozen_oracles()
    entries, rows, enumerations, issues = [], [], [], []
    for case in chosen["cases"]:
        data, entry = api.load_case(case)
        entries.append(entry)
        expected = oracle[case]
        if expected["input_sha256"] != entry["sha256"]:
            raise ValueError("Oracle and input hashes differ: " + case)
        if mode in {"smoke", "correctness"}:
            enumerated = api.enumerate_case(data)
            matches = enumerated["feasible"] == expected["feasible"] and (
                not expected["feasible"] or math.isclose(enumerated["objective"], expected["objective"],
                                                       rel_tol=1e-10, abs_tol=1e-12))
            enumerations.append({"case": case, "matches_frozen_oracle": matches, **enumerated})
            if not matches:
                issues.append({"case": case, "issue": "Fresh enumeration differs from saved oracle"})
        for method in chosen["methods"]:
            result = api.run_method(data, method, config["budgets"])
            checks = api.check_result(data, result, expected)
            if not checks["check_passed"]:
                issues.append({"case": case, "method": method, "issues": checks["issues"]})
            if result["status"] in {"TIMEOUT", "RESOURCE_LIMIT", "ERROR"}:
                issues.append({"case": case, "method": method,
                               "issue": "Representative validation interrupted; see retained record"})
            if method in {"ha_reference", "exact_lc"} or method == "adaptive" and len(data["nodes"]) <= 12:
                if not checks["exact_certificate"] or checks["outcome"] != "MATCHES_ORACLE":
                    issues.append({"case": case, "method": method,
                                   "issue": "Expected an oracle-matching completed exact certificate"})
            rows.append({"case": case, "method": method, "input_sha256": entry["sha256"],
                         "checks": checks, "result": result})
    adverse = config["retained_adverse_case"]
    adverse_records = [row for row in rows if row["case"] == adverse["case"] and row["method"] == "adaptive"]
    if adverse_records:
        row = adverse_records[0]
        observed = row["result"]["common_evaluation"].get("objective")
        retained = (row["checks"]["outcome"] == "SUBOPTIMAL_UNCERTIFIED_WITNESS"
                    and observed is not None and math.isclose(observed, adverse["adaptive_objective"],
                                                             rel_tol=1e-10, abs_tol=1e-12))
        if not retained:
            issues.append({"case": adverse["case"], "issue": "Registered adverse behavior did not reproduce"})
    return {"schema_version": 1, "mode": mode, "scope": chosen["scope"],
            "formal_campaign_rerun": False, "included_frozen_small_inputs": 227,
            "executed_cases": len(entries), "executed_method_calls": len(rows),
            "validation_status": "PASS" if not issues else "FAIL_OR_INCOMPLETE",
            "environment": api.environment(), "budgets": config["budgets"],
            "inputs": entries, "fresh_enumeration_checks": enumerations, "records": rows,
            "negative_outcomes": [{"case": row["case"], "method": row["method"], **row["checks"]}
                                  for row in rows if row["checks"]["outcome"] != "MATCHES_ORACLE"],
            "issues": issues,
            "interpretation": "Heuristic misses and suboptimal witnesses remain visible. PASS means checks and expected adverse behavior reproduced; it does not mean every heuristic found an optimum."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("smoke", "correctness", "caps"))
    parser.add_argument("--output", help="Optional repository-relative JSON under outputs/")
    args = parser.parse_args()
    report = run_mode(args.mode)
    api.emit_report(report, args.output)
    return 0 if report["validation_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
