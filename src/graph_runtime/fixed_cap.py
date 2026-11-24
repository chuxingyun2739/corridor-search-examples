"""Verbatim R3 executed fixed-cap adapter with repository-local imports."""
import math
from pathlib import Path
import sys
import time

def reference_module():
    sys.path.insert(0, str(Path(__file__).absolute().parent / "scripts"))
    import joint_search
    return joint_search


def run_fixed_cap(data, cap, timeout_seconds, limits):
    js = reference_module()
    graph, source, target, specs, cfg = js.load_case_dict(data)
    js.validate_model(graph, cfg, specs)
    start = time.perf_counter()
    result = {"path": [], "support_nodes": [], "stats": dict.fromkeys(js.COUNTERS, 0), "attempts": [],
              "exact_certified": False, "error_message": "", "feasible": None,
              "common_evaluation": {"objective": None}, "scope": "single_fixed_cap_without_adaptive_fallback"}
    try:
        bounds = js.loss_lower_bound(graph, target, cfg)
        label, counters = js.search(graph, source, target, specs, cfg, start + timeout_seconds,
                                    cap=cap, lower_bound=bounds, **limits)
        result["stats"] = counters
        ev = js.common_evaluate(graph, label.path if label else (), label.support_nodes if label else (), specs, cfg, source, target)
        result.update(path=list(label.path) if label else [], support_nodes=list(label.support_nodes) if label else [],
                      feasible=ev["feasible"], common_evaluation=ev,
                      status="COMPLETED_FEASIBLE" if label else "NO_CAPPED_SOLUTION",
                      exact_certified=counters["labels_pruned"] == 0)
        if label and not math.isclose(label.objective, ev["objective"], rel_tol=1e-10, abs_tol=1e-12):
            raise ValueError("Fixed-cap witness objective mismatch")
    except js.SearchLimit as error:
        result.update(status=error.status, stats=error.counters, error_message=str(error))
    result["runtime_ms"] = (time.perf_counter() - start) * 1000
    if result["runtime_ms"] >= timeout_seconds * 1000 and result["status"] not in {"TIMEOUT", "RESOURCE_LIMIT"}:
        result.update(status="TIMEOUT", exact_certified=False, error_message="Deadline exceeded during final evaluation")
    return result
