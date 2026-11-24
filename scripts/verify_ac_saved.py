"""L5: verify selected saved AC evidence with the Python standard library.

This code does not import a power-system model or solver. It checks consistency
of historical saved arrays, flags, controls, identities and scalar arithmetic.
It cannot freshly establish that a network power-flow equation is satisfied.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import stat


DEFAULT_DATA = Path(__file__).absolute().parents[1] / "benchmarks/ac_saved"
PHYSICAL_SUMMARY_FIELDS = (
    "P_loss_AC_MW", "voltage_RMS_deviation", "support_Q_Mvar",
    "redispatch_L1_MW", "Vm_min", "Vm_max", "max_voltage_deviation",
    "voltage_violations", "active_balance_residual_mw",
)


def relative_path(value):
    """Normalize old Windows separators without following external locations."""
    value = str(value).replace("\\", "/")
    path = PurePosixPath(value)
    if (not value or path.is_absolute() or ".." in path.parts
            or any(":" in p or "\x00" in p for p in path.parts)):
        raise ValueError("Unsafe relative evidence path")
    return path.as_posix()


def checked_file(root, relative):
    root = Path(os.path.abspath(root))
    path = root / relative_path(relative)
    if not path.is_relative_to(root):
        raise ValueError("Evidence path is outside its declared data directory")
    for component in (path, *path.parents):
        info = component.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 1024:
            raise ValueError("Linked evidence paths are not accepted")
    return path


def strict_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def nonfinite(_):
        raise ValueError("Nonfinite JSON number")

    return json.loads(data.decode("utf-8-sig"), object_pairs_hook=pairs,
                      parse_constant=nonfinite)


def hash_matches(data, entry):
    return len(data) == entry["bytes"] and hashlib.sha256(data).hexdigest() == entry["sha256"]


def load_bundle(root=DEFAULT_DATA):
    manifest = strict_json(checked_file(root, "manifest.json").read_bytes())
    contents = {}
    for item in manifest["files"]:
        name = relative_path(item["path"])
        if name in contents:
            raise ValueError("Duplicate manifest path")
        raw = checked_file(root, name).read_bytes()
        if not hash_matches(raw, item):
            raise ValueError("SHA256/size mismatch: " + name)
        contents[name] = raw
    records = []
    for entry in manifest["records"]:
        record = {"entry": entry}
        for key in ("method_result", "context", "certificate", "status_controls"):
            location = entry[key]
            record[key] = strict_json(contents[relative_path(location)]) if location else None
        records.append(record)
    return {
        "manifest": manifest,
        "config": strict_json(contents["config.json"]),
        "summary": list(csv.DictReader(io.StringIO(contents["selected_summary.csv"].decode("utf-8-sig")))),
        "records": records,
        "integrity_files_checked": len(contents),
    }


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def finite_tree(value):
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(finite_tree(x) for x in value.values())
    if isinstance(value, list):
        return all(finite_tree(x) for x in value)
    return True


def close(a, b, tolerance):
    return finite(a) and finite(b) and abs(a - b) <= tolerance


class Checks:
    def __init__(self):
        self.items = []

    def add(self, code, passed, record="sample"):
        self.items.append({"record": record, "check": code, "pass": bool(passed)})


def verify_record(record, row, config, checks):
    entry = record["entry"]
    method, context = record["method_result"], record["context"]
    cert, status = record["certificate"], record["status_controls"]
    label = entry["id"]
    add = lambda code, passed: checks.add(code, passed, label)
    protocol = config["historical_protocol"]
    tolerance = config["verification"]["scalar_abs_tolerance"]
    vm_tolerance = config["verification"]["rms_abs_tolerance"]
    cert_tolerance = protocol["certificate_tolerance"]

    add("finite_saved_numbers", finite_tree(record))
    add("record_identity", all(method[k] == entry[k] == row[k] for k in ("scenario_id", "method", "ranker")))
    add("model_identity_metadata", method["model_hash"] == context["model_hash"] == row["model_hash"]
        and method["native_identity"] == context["native_identity"])
    add("frozen_protocol_identity", method["protocol_sha256"] == row["protocol_sha256"] == config["source_protocol_sha256"])
    add("declared_scope", method["graph_support_actions_are_not_AC_controls"] is True
        and method["local_optimum_only"] is True and method["cross_method_cache"] is False)
    add("summary_termination", row["status"] == method["status"]
        and row["certified"] == str(method["certified"])
        and row["failure_reason"] == method["failure_reason"]
        and row["generation_status"] == method["generation_status"])
    add("query_endpoints", int(row["source"]) == method["source"] and int(row["target"]) == method["target"])
    add("recorded_runtime", finite(method["total_runtime"]) and method["total_runtime"] >= 0
        and close(float(row["total_runtime"]), method["total_runtime"], tolerance))
    add("registered_resource_configuration", method["candidate_cap"] == protocol["max_candidates"]
        and method["method_budget_s"] == protocol["method_wall_seconds"]
        and method["max_optimizer_calls"] == protocol["max_optimizer_calls"]
        and method["max_total_ac_calls"] == protocol["max_total_ac_calls"]
        and method["redispatch_fraction_load"] == protocol["redispatch_fraction_load"])

    events = method["events"]
    accepted = [e for e in events if e.get("certified") is True]
    add("recorded_event_counts", len(events) == int(row["recorded_stage_count"])
        and len(accepted) == int(row["accepted_stage_count"]))
    pf_calls = sum(method[k] for k in ("certificate_pf_count", "reference_pf_count", "sensitivity_pf_count"))
    ledger = method["call_budget_reconciliation"]
    add("saved_call_accounting", method["AC_solve_count"] == method["optimizer_solve_count"] + pf_calls
        and ledger["optimizer_recorded_calls"] == method["optimizer_solve_count"]
        and ledger["pf_recorded_calls"] == pf_calls and ledger["ledger_reconciled"] is True
        and method["call_budget_verified"] is True)
    add("saved_call_limits", 0 <= method["optimizer_solve_count"] <= method["max_optimizer_calls"]
        and 0 <= method["AC_solve_count"] <= method["max_total_ac_calls"])

    candidates = [c for c in method["candidates"] if c.get("path")]
    demand = {int(k): v for k, v in context["demand"].items()}
    for candidate in candidates:
        interior = set(candidate["path"][1:-1]) & set(context["eligible"])
        mapped = sorted(interior, key=lambda node: (-demand.get(node, 0), node))[:protocol["max_hosts"]]
        add("candidate_host_mapping:" + str(candidate["candidate_slot"]), mapped == candidate["hosts"])
        add("candidate_endpoints:" + str(candidate["candidate_slot"]), candidate["path"][0] == method["source"]
            and candidate["path"][-1] == method["target"])

    selected = method["selected"]
    add("selection_certification_agreement", method["certified"] is bool(selected))
    configured_cap = float(row["native_load_MW"]) * method["redispatch_fraction_load"]
    add("configured_redispatch_cap", close(configured_cap, float(row["redispatch_limit_MW"]), tolerance))
    if not selected:
        add("uncertified_metrics_remain_missing", method["metrics"] is None
            and all(row[k] == "" for k in PHYSICAL_SUMMARY_FIELDS))
        add("uncertified_has_no_selected_files", cert is None and status is None
            and entry["certificate"] is None and entry["status_controls"] is None)
        add("resource_limit_is_not_infeasibility", method["status"] == "RESOURCE_LIMIT"
            and not accepted and row["accepted_stage"] == "" and row["selected_candidate_slot"] == "")
        return {"id": label, "status": method["status"], "certified": False,
                "P_loss_AC_MW": None, "support_Q_Mvar": None, "voltage_RMS_deviation": None}

    if cert is None or status is None:
        add("selected_files_present", False)
        return {"id": label, "status": method["status"], "certified": True}
    add("selected_files_present", True)
    cm, controls = cert["metrics"], status["controls"]
    add("selected_file_identity", relative_path(selected["certificate_file"]) == entry["certificate"]
        and relative_path(status["raw_folder"]) == str(PurePosixPath(entry["certificate"]).parent))
    add("selected_status_identity", status["scenario_id"] == method["scenario_id"]
        and status["attempt_id"] == selected["attempt_id"] and status["stage"] == selected["stage"] == "B_LOSS"
        and status["network"] == row["system"])
    add("certificate_embedded_in_status", status["certificate"] == cert)
    add("certificate_protocol_identity", cert["protocol_sha256"] == method["protocol_sha256"])
    add("saved_acceptance_flags", all(cert[k] is True for k in
        ("PF_converged", "optimizer_converged", "certificate_pass", "finite_checks_pass"))
        and status["optimizer_converged"] is True
        and all(selected[k] is True for k in ("certified", "physical_certificate_pass", "optimizer_converged", "on_time"))
        and cert["strict_by_tolerance"]["1e-06"] is True
        and cert["input_checks"] and all(x is True for x in cert["input_checks"].values()))
    add("saved_residual_tolerance", all(finite(x) and abs(x) <= cert_tolerance for x in (
        cert["max_required_residual"], cert["nodal_PQ_max_mva"], selected["max_required_residual"],
        status["optimization_balance_max_mva"], status["constraint_residual_proxy"])))
    add("selected_event_membership", any(e == selected for e in events))
    matches = [c for c in candidates if c["candidate_slot"] == selected["candidate_slot"]]
    add("selected_candidate_identity", len(matches) == 1 and matches[0]["path"] == selected["path"]
        and set(matches[0]["hosts"]) == set(selected["hosts"])
        and matches[0]["unique_solve_id"] == selected["unique_solve_id"])
    add("selected_acceptance_time", selected["completed_method_seconds"] <= method["method_budget_s"]
        and 0 <= selected["started_method_seconds"] <= selected["completed_method_seconds"])
    add("selected_summary_stage", row["accepted_stage"] == selected["stage"]
        and int(row["selected_candidate_slot"]) == selected["candidate_slot"])
    add("selected_metrics_agreement", selected["metrics"] == method["metrics"])

    nodes, q_values = controls["nodes"], controls["Q_support_mvar"]
    q_total = math.fsum(q_values)
    add("support_locations", len(nodes) == len(q_values) == len(set(nodes)) <= protocol["max_hosts"]
        and set(nodes) == set(selected["hosts"]))
    add("support_Q_bounds", all(-tolerance <= q <= protocol["Q_each_mvar"] + tolerance for q in q_values)
        and q_total <= protocol["Q_total_mvar"] + tolerance)
    add("selected_support_controls", len(selected["support_controls"]) == len(q_values)
        and all(close(x, y, tolerance) for x, y in zip(selected["support_controls"], q_values)))
    add("saved_support_checks", cm["support_Q_violations"] == cm["support_P_violations"] == 0
        and close(q_total, cm["support_total_Q_mvar"], tolerance)
        and close(q_total, status["metrics"]["support_Q_mvar"], tolerance))

    generation = {g["generator_id"]: g for g in cert["generation"]}
    command = {g["kind"] + ":" + str(g["index"]): g for g in controls["generation"]}
    reference = {g["generator_id"]: g for g in context["reference"]["certificate"]["generation"]}
    add("generation_identity", len(generation) == len(cert["generation"])
        and len(command) == len(controls["generation"]) and set(generation) == set(command) == set(reference))
    for generator_id, g in generation.items():
        if generator_id not in command or generator_id not in reference:
            continue
        cmd, ref = command[generator_id], reference[generator_id]
        add("generation_command:" + generator_id, cmd["bus"] == g["bus"] == ref["bus"]
            and all(close(cmd[k], g[k], tolerance) for k in ("P_mw", "Q_mvar", "Vm"))
            and close(cmd["reference"], ref["P_mw"], tolerance))
        add("native_generation_bounds:" + generator_id,
            all(g[k] == ref[k] for k in ("Pmin_mw", "Pmax_mw", "Qmin_mvar", "Qmax_mvar"))
            and g["Pmin_mw"] - tolerance <= g["P_mw"] <= g["Pmax_mw"] + tolerance
            and g["Qmin_mvar"] - tolerance <= g["Q_mvar"] <= g["Qmax_mvar"] + tolerance)
    if set(generation) != set(reference):
        return {"id": label, "status": method["status"], "certified": True}
    l1 = math.fsum(abs(g["P_mw"] - reference[k]["P_mw"]) for k, g in generation.items())
    add("redispatch_L1", close(l1, status["metrics"]["L1_mw"], tolerance)
        and close(configured_cap, status["l1_limit_mw"], tolerance)
        and l1 <= configured_cap + tolerance)

    vm_map = cm["vm_by_bus"]
    vm_values = list(vm_map.values())
    bus_count = {"ieee30": 30, "ieee57": 57}[row["system"]]
    add("voltage_vector_identity", set(vm_map) == {str(n) for n in range(bus_count)}
        and len(controls["Vm_pu"]) == bus_count
        and all(close(v, controls["Vm_pu"][int(bus)], tolerance) for bus, v in vm_map.items()))
    rms = math.sqrt(math.fsum((v - 1) ** 2 for v in vm_values) / len(vm_values))
    derived = dict(P_loss_AC_MW=cm["active_loss_MW"], support_Q_Mvar=q_total, redispatch_L1_MW=l1,
                   Vm_min=min(vm_values), Vm_max=max(vm_values), voltage_RMS_deviation=rms,
                   max_voltage_deviation=max(abs(v - 1) for v in vm_values))
    for k, value in derived.items():
        tol = vm_tolerance if k in {"Vm_min", "Vm_max", "voltage_RMS_deviation", "max_voltage_deviation"} else tolerance
        add("reaggregated_metric:" + k, close(value, method["metrics"][k], tol)
            and close(value, float(row[k]), tol))
    add("voltage_saved_extrema", close(min(vm_values), cm["min_voltage"], vm_tolerance)
        and close(max(vm_values), cm["max_voltage"], vm_tolerance)
        and cm["voltage_violations"] == int(row["voltage_violations"]) == 0)
    for kind in ("line", "transformer"):
        loading, limits = cm[kind + "_loading_by_id"], cm[kind + "_limit_by_id"]
        add("saved_thermal_limits:" + kind, set(loading) == set(limits)
            and all(0 <= loading[k] <= limits[k] + tolerance for k in loading)
            and cm[kind + "_violations"] == cm[kind + "_missing_results"] == 0)
    generation_total = math.fsum(g["P_mw"] for g in generation.values())
    balance = generation_total - cm["total_load_mw"] - cm["active_loss_MW"]
    add("saved_active_balance_arithmetic", close(generation_total, cm["total_generation_mw"], tolerance)
        and close(cm["total_load_mw"], float(row["native_load_MW"]), tolerance)
        and close(balance, cm["active_balance_residual_MW"], tolerance)
        and close(balance, float(row["active_balance_residual_mw"]), tolerance)
        and abs(balance) <= cert_tolerance)
    add("saved_loss_objective", close(status["objective"], cm["active_loss_MW"], tolerance)
        and close(method["metrics"]["branch_active_loss_mw"], cm["active_loss_MW"], tolerance)
        and close(method["metrics"]["P_loss_pct_load"], 100 * cm["active_loss_MW"] / cm["total_load_mw"], tolerance))
    graph_nodes = matches[0].get("support_nodes", []) if matches else []
    return {"id": label, "status": method["status"], "certified": True, **derived,
            "graph_support_nodes": graph_nodes, "AC_hosts": nodes,
            "graph_support_equals_AC_hosts": set(graph_nodes) == set(nodes),
            "AC_Q_each_Mvar": q_values}


def verify_bundle(bundle):
    checks = Checks()
    manifest, config = bundle["manifest"], bundle["config"]
    checks.add("manifest_scope", manifest["level"] == "L5" and manifest["schema_version"] == 1)
    checks.add("integrity_census", bundle["integrity_files_checked"] == len(manifest["files"]) == 20)
    checks.add("checker_tolerances", config["verification"]["scalar_abs_tolerance"] == 1e-6
               and config["verification"]["rms_abs_tolerance"] == 1e-9
               and config["historical_protocol"]["certificate_tolerance"] == 1e-6)
    rows = {(r["scenario_id"], r["ranker"], r["method"]): r for r in bundle["summary"]}
    identities = {(r["entry"]["scenario_id"], r["entry"]["ranker"], r["entry"]["method"]) for r in bundle["records"]}
    checks.add("five_summary_identities", len(rows) == len(bundle["summary"]) == len(bundle["records"]) == 5
               and identities == set(rows))
    values = []
    for record in bundle["records"]:
        e = record["entry"]
        row = rows[e["scenario_id"], e["ranker"], e["method"]]
        values.append(verify_record(record, row, config, checks))
    methods = [r["method_result"] for r in bundle["records"]]
    observed = {
        "method_records": len(methods),
        "selected_certificates": sum(m["certified"] is True for m in methods),
        "context_projections": len(bundle["records"]),
        "candidate_mappings": sum(bool(c.get("path")) for m in methods for c in m["candidates"]),
        "recorded_events": sum(len(m["events"]) for m in methods),
        "accepted_events": sum(e.get("certified") is True for m in methods for e in m["events"]),
        "terminal_status_counts": dict(Counter(m["status"] for m in methods)),
        "certified_resource_limit_records": sum(m["status"] == "RESOURCE_LIMIT" and m["certified"] for m in methods),
        "uncertified_resource_limit_records": sum(m["status"] == "RESOURCE_LIMIT" and not m["certified"] for m in methods),
    }
    checks.add("illustrative_sample_census", observed == manifest["expected"])
    failures = [c for c in checks.items if not c["pass"]]
    return {
        "status": "FAIL" if failures else "PASS", "level": "L5", "L6_supported": False,
        "files_sha256_checked": bundle["integrity_files_checked"],
        "arithmetic_identity_checks": len(checks.items), "passed_checks": len(checks.items) - len(failures),
        "failed_checks": len(failures), "failures": failures, "observed": observed, "saved_values": values,
        "scope": "Selected saved evidence consistency only; no AC optimizer, power flow, independent physical replay or global optimality proof",
        "publication_status": manifest["publication_status"],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    args = parser.parse_args(argv)
    try:
        result = verify_bundle(load_bundle(args.data_dir))
    except (OSError, KeyError, ValueError, TypeError, IndexError, ZeroDivisionError) as exc:
        result = {"status": "FAIL", "level": "L5", "L6_supported": False,
                  "error_type": type(exc).__name__, "error": "Evidence could not be loaded or validated; check fixture schema and integrity"}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
