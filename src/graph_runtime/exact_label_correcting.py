"""Independent FIFO label-correcting adaptation motivated by Feillet et al. (2004).

This is NOT a reproduction of that paper: its full text was not available for
verification. See configs/graph/EXACT_LC_ADAPTATION.md.
Only the frozen model, transition functions, label representation, validation,
and common evaluator are reused. Search, admission, dominance, queue handling,
termination, and interrupted-run reporting are implemented independently here.

Scope: elementary paths, fixed nonnegative P/Q and r/x, operational voltage
bounds containing Vnom, nonnegative loss/support costs, and the frozen binary
no-support / bounded-support action policy. Higher positive sending voltage
increases V-(rP+xQ)/V and decreases both branch losses. All reachable operational
voltages are <= Vnom; min(Vnom, raw+C) is monotone in raw, while used capacity
and its nonnegative cost are nonincreasing. Thus the conservative continuation
dominance below is valid under the shared model's validation assumptions.

No numerical epsilon, voltage discretization, label cap, resource-based
unreachability, A* bound, or first-goal termination is used. An exact certificate
requires FIFO queue exhaustion and successful independent witness evaluation.
"""
from collections import deque
import itertools
import math
from pathlib import Path
import sys
import time


_REFERENCE = Path(__file__).absolute().parent
sys.path.insert(0, str(_REFERENCE / "scripts"))
from joint_search import validate_model
from evidence_core import load_case_dict, common_evaluate
from src.round5.vamls import Label, support_arrivals, apply_source_support_options
from src.round5.power_flow_approximation import BranchPowerPU, evaluate_branch_pu


METHOD = "independent_exact_label_correcting"
COUNTERS = ("labels_generated", "labels_expanded", "labels_dominated", "labels_pruned",
            "max_active_labels", "branches_evaluated", "support_labels_generated")
SCOPE = "same_joint_elementary_path_voltage_state_support_action_search"


class _BudgetReached(RuntimeError):
    def __init__(self, status, message):
        self.status = status
        super().__init__(message)


def _continuation_covers(a, b):
    """Same-node safe continuation inclusion; ties retain one representative.

The two history inclusions keep every elementary extension and future support
choice available. Componentwise cumulative costs, voltage, and device budget
then preserve feasibility and objective ordering for the same continuation.
Support-history inclusion and the separate loss/cost comparisons are deliberately
more restrictive than the minimum sufficient state for this particular model.
"""
    return (
        a.node == b.node
        and a.visited_nodes.issubset(b.visited_nodes)
        and set(a.support_nodes).issubset(b.support_nodes)
        and a.active_loss_pu <= b.active_loss_pu
        and a.reactive_loss_pu <= b.reactive_loss_pu
        and a.support_cost <= b.support_cost
        and a.support_count <= b.support_count
        and a.voltage_pu >= b.voltage_pu
    )


def run(data, timeout_seconds=10.0, max_expansions=20000,
        max_labels=60000, max_resident=20000):
    """Return the joint_search.run result schema with a distinct method name.

Limits are global hard budgets, never per-node heuristic caps. A budget is
checked before admitting another counted label / expansion / resident label.
TIMEOUT, RESOURCE_LIMIT, and ERROR preserve any already validated incumbent;
without one, feasibility is unknown. Only complete exhaustion certifies an
optimum or infeasibility within the stated fixed-transfer arithmetic model.
    """
    graph, source, target, specs, cfg = load_case_dict(data)
    validate_model(graph, cfg, specs)
    if source not in graph.nodes or target not in graph.nodes:
        raise ValueError("Source and target must belong to the graph")
    if not math.isfinite(timeout_seconds) or timeout_seconds < 0:
        raise ValueError("Nonnegative finite time budget required")
    if any(not isinstance(v, int) or v < 1 for v in
           (max_expansions, max_labels, max_resident)):
        raise ValueError("Positive integer search budgets required")

    # Match the archived run's timing boundary: decoded model validation precedes
    # the query timer; all search work and common evaluation are timed.
    started = time.perf_counter()
    deadline = started + timeout_seconds
    counters = dict.fromkeys(COUNTERS, 0)
    identifiers = itertools.count()
    fifo = deque()
    resident = {}
    live = {}
    best = best_evaluation = None
    bound_prunes = 0
    exhausted = False
    status, error = "RUNNING", ""
    power = BranchPowerPU(cfg.p_transfer_pu, cfg.q_transfer_pu)

    def check_time():
        if time.perf_counter() >= deadline:
            raise _BudgetReached("TIMEOUT", "Predefined query time budget exhausted")

    def count_generated():
        check_time()
        if counters["labels_generated"] >= max_labels:
            raise _BudgetReached("RESOURCE_LIMIT", "Global generated-label budget exhausted")
        counters["labels_generated"] += 1

    def admit(candidate, used_support=False):
        nonlocal best, best_evaluation, bound_prunes
        count_generated()
        counters["support_labels_generated"] += int(used_support)
        quantities = (candidate.objective, candidate.voltage_pu,
                      candidate.active_loss_pu, candidate.reactive_loss_pu,
                      candidate.support_cost, candidate.min_voltage_pu,
                      candidate.min_pre_support_voltage_pu)
        if not all(math.isfinite(v) for v in quantities):
            raise OverflowError("Nonfinite label resource; no exact certificate")

        # Validate at discovery, before another queue entry or resource limit can
        # interrupt the run. An interrupted run can then return this witness.
        if candidate.node == target and (best is None or candidate.objective < best.objective):
            evaluation = common_evaluate(graph, candidate.path, candidate.support_nodes,
                                         specs, cfg, source, target)
            if (not evaluation["feasible"]
                    or not math.isfinite(evaluation["objective"])
                    or not math.isclose(candidate.objective, evaluation["objective"],
                                        rel_tol=1e-10, abs_tol=1e-12)):
                raise RuntimeError("Label witness disagrees with independent common evaluator")
            best, best_evaluation = candidate, evaluation
            check_time()

        # Objective increments are nonnegative. Strict comparison also retains
        # all ties. This is exact bounding, not a heuristic label deletion.
        if best is not None and candidate.objective > best.objective:
            bound_prunes += 1
            return
        group = resident.setdefault(candidate.node, {})
        removal = []
        for identifier, other in group.items():
            check_time()
            if _continuation_covers(other, candidate):
                counters["labels_dominated"] += 1
                return
            if _continuation_covers(candidate, other):
                removal.append(identifier)
        if len(live) - len(removal) + 1 > max_resident:
            raise _BudgetReached("RESOURCE_LIMIT", "Global resident-label budget exhausted")
        for identifier in removal:
            del group[identifier]
            del live[identifier]
        counters["labels_dominated"] += len(removal)
        group[candidate.label_id] = candidate
        live[candidate.label_id] = candidate
        fifo.append(candidate.label_id)
        counters["max_active_labels"] = max(counters["max_active_labels"], len(live))

    try:
        check_time()
        for voltage, selected, cost, used in apply_source_support_options(
                source, target, specs, cfg):
            admit(Label(next(identifiers), source, cost, 0.0, 0.0, voltage, voltage,
                        len(selected), cost, selected, frozenset({source}), (source,),
                        None, cfg.nominal_voltage_pu), used)
        while fifo:
            check_time()
            identifier = fifo.popleft()
            label = live.get(identifier)
            if label is None:
                continue  # A later label dominated this pending entry.
            if best is not None and label.objective > best.objective:
                bound_prunes += 1
                continue
            if counters["labels_expanded"] >= max_expansions:
                raise _BudgetReached("RESOURCE_LIMIT", "Global label-expansion budget exhausted")
            counters["labels_expanded"] += 1
            if label.node == target:
                continue  # A FIFO goal is only an incumbent, never a stop rule.
            for branch in graph.neighbors(label.node):
                check_time()
                counters["branches_evaluated"] += 1
                if branch.target in label.visited_nodes:
                    continue
                result = evaluate_branch_pu(branch, label.voltage_pu, power)
                if not all(math.isfinite(v) for v in
                           (result.active_loss_pu, result.reactive_loss_pu,
                            result.arrival_voltage_pu, result.current_pu,
                            result.voltage_drop_pu, result.apparent_power_pu)):
                    raise OverflowError("Nonfinite branch resource; no exact certificate")
                if result.capacity_violation:
                    continue
                for voltage, selected, cost, used in support_arrivals(
                        branch.target, result.arrival_voltage_pu, label.support_nodes,
                        specs, cfg, source, target):
                    check_time()
                    if not cfg.voltage_lower_bound <= voltage <= cfg.voltage_upper_bound:
                        continue
                    loss_p = label.active_loss_pu + result.active_loss_pu
                    loss_q = label.reactive_loss_pu + result.reactive_loss_pu
                    support_cost = label.support_cost + cost
                    candidate = Label(
                        next(identifiers), branch.target, loss_p + support_cost,
                        loss_p, loss_q, voltage, min(label.min_voltage_pu, voltage),
                        len(selected), support_cost, selected,
                        label.visited_nodes | {branch.target},
                        label.path + (branch.target,), identifier,
                        min(label.min_pre_support_voltage_pu, result.arrival_voltage_pu))
                    admit(candidate, used)
        check_time()
        exhausted = True
        status = "COMPLETED_FEASIBLE" if best is not None else "COMPLETED_INFEASIBLE"
    except _BudgetReached as exc:
        status, error = exc.status, str(exc)
    except Exception as exc:
        status, error = "ERROR", repr(exc)

    if best_evaluation is None:
        best_evaluation = common_evaluate(graph, (), (), specs, cfg, source, target)
    elapsed = time.perf_counter() - started
    if status.startswith("COMPLETED") and elapsed >= timeout_seconds:
        status, error = "TIMEOUT", "Predefined deadline expired during final common evaluation"
    completed = exhausted and status.startswith("COMPLETED")
    if not completed and best is None:
        best_evaluation["feasible"] = None
    return {
        "case": data["case"], "method": METHOD, "status": status,
        "runtime_ms": elapsed * 1000, "feasible": best_evaluation["feasible"],
        "path": list(best.path) if best is not None else [],
        "support_nodes": list(best.support_nodes) if best is not None else [],
        "common_evaluation": best_evaluation, "stats": counters,
        "attempts": [{"cap": None, "status": status, "queue_policy": "FIFO",
                      "queue_exhausted": exhausted, "wall_ms": elapsed * 1000,
                      "objective": best_evaluation["objective"],
                      "incumbent_bound_prunes": bound_prunes,
                      "stats": dict(counters)}],
        "error_message": error, "exact_certified": bool(completed), "scope": SCOPE,
    }
