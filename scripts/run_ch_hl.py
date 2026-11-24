"""Check archived CH/HL on a small fixed set of authored graphs, all ordered pairs."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).absolute().parents[1] / "src"))
from graph_runtime import api
from graph_runtime.static_checks import ENGINES, check_engine, nominal_loss_graph


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="Optional repository-relative JSON under outputs/")
    args = parser.parse_args()
    config = api.settings()["ch_hl"]
    records, issues = [], []
    for case in config["cases"]:
        data, entry = api.load_case(case)
        edges, nodes = nominal_loss_graph(data)
        for engine in ENGINES:
            try:
                result = check_engine(engine, edges, nodes, **config["budgets"])
            except Exception as error:
                result = {"engine": engine.__name__, "validation_status": "ERROR", "query_count": 0,
                          "error": type(error).__name__ + ": " + str(error)}
            records.append({"case": case, "input_sha256": entry["sha256"] , **result})
            if result["validation_status"] != "PASS":
                issues.append({"case": case, "engine": engine.__name__, "details": result})
    report = {"schema_version": 1, "scope": config["scope"], "formal_campaign_rerun": False,
              "environment": api.environment(), "cases": len(config["cases"]),
              "query_count": sum(record["query_count"] for record in records),
              "validation_status": "PASS" if not issues else "FAIL", "records": records,
              "issues": issues,
              "limitations": "These are static nominal-loss shortest paths. They do not establish voltage/support feasibility or optimality for the state-dependent electrical model."}
    api.emit_report(report, args.output)
    return 0 if report["validation_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
