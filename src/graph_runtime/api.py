"""Repository-local input loading and dispatch; no replacement search algorithm."""
from copy import deepcopy
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import math
from pathlib import Path
import platform
import sys
import time

HERE = Path(__file__).absolute().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "scripts"))
import joint_search
import exact_label_correcting
from fixed_cap import run_fixed_cap
from src.round5.exact_enumeration import exact_enumeration

ALIASES = {
    "ha_reference": "history_aware_reference_search",
    "adaptive": "adaptive_label_management_search",
}
CAPS = (3, 5, 10, 20, 40)


def read_json(relative):
    path = (REPO / relative).absolute()
    if not path.is_relative_to(REPO):
        raise ValueError("Input must be inside the repository")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def environment():
    packages = {}
    for name in ("networkx", "psutil"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    return {"python": platform.python_version(), "implementation": platform.python_implementation(),
            "system": platform.system(), "machine": platform.machine(), "packages": packages}


def settings():
    return read_json("configs/graph/run_modes.json")


def input_entries():
    entries = read_json("benchmarks/graph/frozen_inputs.json")["inputs"]
    by_case = {entry["case"]: entry for entry in entries}
    if len(by_case) != len(entries):
        raise ValueError("Duplicate case identity in frozen input registry")
    return by_case


def load_case(case):
    entry = input_entries()[case]
    data_bytes = (REPO / entry["path"]).read_bytes()
    if hashlib.sha256(data_bytes).hexdigest() != entry["sha256"]:
        raise ValueError("Frozen graph input hash mismatch: " + case)
    data = json.loads(data_bytes)
    if data["case"] != case or len(data["nodes"]) != entry["nodes"]:
        raise ValueError("Frozen graph input identity mismatch: " + case)
    return data, entry


def frozen_oracles():
    values = {row["case"]: row for row in read_json("benchmarks/graph/oracle_227.json")}
    adverse = read_json("benchmarks/graph/adversarial_13_reference.json")
    case = adverse["case"]["case"]
    values[case] = {"case": case, "feasible": True,
                    "objective": adverse["independent_exact_objective"],
                    "path": adverse["independent_exact_path"],
                    "input_sha256": input_entries()[case]["sha256"],
                    "reference_kind": "separate_saved_independent_adverse_oracle"}
    smoke = settings()["smoke_expected"]
    values[smoke["case"]] = {**smoke, "feasible": True,
                             "input_sha256": input_entries()[smoke["case"]]["sha256"]}
    return values


def enumerate_case(data):
    graph, source, target, specs, cfg = joint_search.load_case_dict(data)
    result = exact_enumeration(graph, source, target, specs, cfg, max_depth=len(graph.nodes))
    return {"feasible": result.feasible,
            "objective": result.objective if result.feasible else None,
            "path": list(result.path), "support_nodes": list(result.support_nodes),
            "combinations_evaluated": result.combinations_evaluated,
            "runtime_seconds": result.runtime_seconds}


def run_method(data, method, budgets):
    """Dispatch genuine archived cores; preserve failures and unknown outcomes."""
    limits = {name: budgets[name] for name in ("max_expansions", "max_labels", "max_resident")}
    started = time.perf_counter()
    try:
        if method in ALIASES:
            result = joint_search.run(deepcopy(data), ALIASES[method],
                                      timeout_seconds=budgets["timeout_seconds"], **limits)
        elif method == "exact_lc":
            result = exact_label_correcting.run(deepcopy(data),
                                               timeout_seconds=budgets["timeout_seconds"], **limits)
        elif method.startswith("cap_") and int(method[4:]) in CAPS:
            result = run_fixed_cap(deepcopy(data), int(method[4:]), budgets["timeout_seconds"], limits)
        else:
            raise ValueError("Unsupported method: " + method)
    except Exception as error:
        result = {"case": data["case"], "method": method, "status": "ERROR", "feasible": None,
                  "path": [], "support_nodes": [], "common_evaluation": {"objective": None},
                  "stats": {}, "attempts": [], "exact_certified": False,
                  "runtime_ms": (time.perf_counter() - started) * 1000,
                  "error_message": type(error).__name__ + ": " + str(error)}
    result["public_method_alias"] = method
    return result


def check_result(data, result, oracle):
    """Independently reevaluate witnesses and distinguish exact and heuristic outcomes."""
    errors = []
    witness = result.get("feasible") is True
    reported = result.get("common_evaluation", {}).get("objective")
    exact = bool(result.get("exact_certified"))
    status = result.get("status")
    completed = status in {"COMPLETED_FEASIBLE", "COMPLETED_INFEASIBLE", "NO_CAPPED_SOLUTION"}
    if exact and not completed:
        errors.append("An interrupted/error run cannot carry an exact certificate")
    if witness:
        graph, source, target, specs, cfg = joint_search.load_case_dict(data)
        checked = joint_search.common_evaluate(graph, result.get("path", []),
                                              result.get("support_nodes", []), specs, cfg, source, target)
        if not checked["feasible"]:
            errors.append("Returned witness fails the independent common evaluator")
        elif reported is None or not math.isfinite(reported) or not math.isclose(
                reported, checked["objective"], rel_tol=1e-10, abs_tol=1e-12):
            errors.append("Reported objective disagrees with common evaluation")
    elif result.get("path"):
        errors.append("A nonempty path is not marked as a feasible witness")
    gap = reported - oracle["objective"] if witness and reported is not None and oracle["feasible"] else None
    if exact and (witness != oracle["feasible"] or gap is not None and abs(gap) > 1e-8):
        errors.append("Exact certificate disagrees with the frozen independent oracle")
    if witness and not oracle["feasible"]:
        errors.append("A feasible witness contradicts the frozen infeasibility oracle")
    if gap is not None and gap < -1e-8:
        errors.append("Witness improves the frozen oracle; reference requires review")
    if status == "ERROR":
        outcome = "EXECUTION_ERROR"
    elif status in {"TIMEOUT", "RESOURCE_LIMIT"}:
        outcome = "LIMIT_WITH_WITNESS" if witness else "UNKNOWN_AFTER_LIMIT"
    elif oracle["feasible"] and not witness:
        outcome = "COMPLETED_NO_WITNESS_ON_KNOWN_FEASIBLE"
    elif gap is not None and gap > 1e-8:
        outcome = "SUBOPTIMAL_UNCERTIFIED_WITNESS" if not exact else "INVALID_CERTIFICATE"
    else:
        outcome = "MATCHES_ORACLE"
    relative = None if gap is None or oracle["objective"] == 0 else 100.0 * gap / abs(oracle["objective"])
    return {"check_passed": not errors, "issues": errors, "outcome": outcome,
            "feasible_witness": witness, "exact_certificate": exact,
            "objective_gap": gap, "optimality_gap_percent": relative,
            "oracle_objective": oracle["objective"], "oracle_feasible": oracle["feasible"]}


def emit_report(report, output=None):
    """Write optional local results only; never modify frozen inputs or references."""
    text = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if output:
        destination = (REPO / output).absolute()
        result_root = REPO / "outputs"
        if not destination.is_relative_to(result_root) or ".." in Path(output).parts:
            raise ValueError("--output must be a repository-relative path inside outputs/")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
    print(text, end="")
