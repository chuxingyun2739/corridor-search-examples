from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .models import GraphPU, LoadPU, SupportSpec
from .power_flow_approximation import BranchPowerPU, evaluate_branch_pu


@dataclass(frozen=True)
class VAMLSConfig:
    nominal_voltage_pu: float = 1.0
    voltage_lower_bound: float = 0.90
    voltage_upper_bound: float = 1.10
    max_support_nodes: int = 2
    p_transfer_pu: float = 0.10
    q_transfer_pu: float = 0.03
    lambda_support_count: float = 0.01
    lambda_support_capacity: float = 0.0
    dominance_eps: float = 1e-10
    heuristic_label_cap: Optional[int] = None
    allow_support_at_source: bool = False
    allow_support_at_target: bool = False


@dataclass
class Label:
    label_id: int
    node: int
    objective: float
    active_loss_pu: float
    reactive_loss_pu: float
    voltage_pu: float
    min_voltage_pu: float
    support_count: int
    support_cost: float
    support_nodes: Tuple[int, ...]
    visited_nodes: frozenset[int]
    path: Tuple[int, ...]
    parent_label_id: Optional[int]
    min_pre_support_voltage_pu: float = 1.0


@dataclass
class VAMLSResult:
    feasible: bool
    best_label: Optional[Label]
    expanded_labels: int
    generated_labels: int
    dominated_labels: int
    constraint_pruned_labels: int
    heuristic_pruned_labels: int
    support_actions: int
    voltage_violation_pu: float
    max_active_labels: int
    branches_evaluated: int
    labels_dominated_by_exact_rule: int = 0
    labels_rejected_as_dominated: int = 0
    labels_removed_by_heuristic_cap: int = 0
    support_action_labels_generated: int = 0
    support_actions_in_best_solution: int = 0


@dataclass
class _Counters:
    ids: itertools.count = field(default_factory=lambda: itertools.count())
    expanded: int = 0
    generated: int = 0
    dominated: int = 0
    constraint: int = 0
    heuristic: int = 0
    support_actions: int = 0
    branches_evaluated: int = 0
    max_active_labels: int = 0
    labels_dominated_by_exact_rule: int = 0
    labels_rejected_as_dominated: int = 0
    labels_removed_by_heuristic_cap: int = 0
    support_action_labels_generated: int = 0


def is_support_action_allowed(
    node: int,
    source: int,
    target: int,
    config: VAMLSConfig,
) -> bool:
    if node == source and not config.allow_support_at_source:
        return False
    if node == target and not config.allow_support_at_target:
        return False
    return True


def dominates(a: Label, b: Label, eps: float = 1e-10, history_aware: bool = True) -> bool:
    if a.node != b.node:
        return False
    if history_aware:
        if not a.visited_nodes.issubset(b.visited_nodes):
            return False
        if not set(a.support_nodes).issubset(set(b.support_nodes)):
            return False
    no_worse = (
        a.active_loss_pu <= b.active_loss_pu + eps
        and a.reactive_loss_pu <= b.reactive_loss_pu + eps
        and a.voltage_pu >= b.voltage_pu - eps
        and a.support_count <= b.support_count
        and a.support_cost <= b.support_cost + eps
    )
    better = (
        a.active_loss_pu < b.active_loss_pu - eps
        or a.reactive_loss_pu < b.reactive_loss_pu - eps
        or a.voltage_pu > b.voltage_pu + eps
        or a.support_count < b.support_count
        or a.support_cost < b.support_cost - eps
    )
    return no_worse and better


def support_arrivals(
    node: int,
    raw_voltage_pu: float,
    selected: Tuple[int, ...],
    support_specs: Dict[int, SupportSpec],
    config: VAMLSConfig,
    source: Optional[int] = None,
    target: Optional[int] = None,
) -> List[Tuple[float, Tuple[int, ...], float, bool]]:
    options = [(raw_voltage_pu, selected, 0.0, False)]
    if source is not None and target is not None and not is_support_action_allowed(node, source, target, config):
        return options
    spec = support_specs.get(node)
    if (
        spec
        and spec.available
        and node not in selected
        and len(selected) < config.max_support_nodes
        and spec.capacity_pu > 0
    ):
        supported = min(config.nominal_voltage_pu, raw_voltage_pu + spec.capacity_pu)
        used = max(0.0, supported - raw_voltage_pu)
        cost = config.lambda_support_count + spec.fixed_cost + config.lambda_support_capacity * used + spec.unit_cost * used
        options.append((supported, tuple(sorted(selected + (node,))), cost, True))
    return options


def apply_source_support_options(
    source: int,
    target: int,
    support_specs: Dict[int, SupportSpec],
    config: VAMLSConfig,
) -> List[Tuple[float, Tuple[int, ...], float, bool]]:
    if not is_support_action_allowed(source, source, target, config):
        return [(config.nominal_voltage_pu, (), 0.0, False)]
    return support_arrivals(
        source,
        config.nominal_voltage_pu,
        (),
        support_specs,
        config,
        source,
        target,
    )


def insert_label(
    labels: Dict[int, List[Label]],
    candidate: Label,
    config: VAMLSConfig,
    history_aware: bool = True,
) -> Tuple[bool, int, int, int]:
    existing = labels.setdefault(candidate.node, [])
    if any(dominates(label, candidate, config.dominance_eps, history_aware) for label in existing):
        return False, 0, 0, 1
    removed = sum(1 for label in existing if dominates(candidate, label, config.dominance_eps, history_aware))
    labels[candidate.node] = [
        label for label in existing if not dominates(candidate, label, config.dominance_eps, history_aware)
    ]
    labels[candidate.node].append(candidate)
    if config.heuristic_label_cap is not None and len(labels[candidate.node]) > config.heuristic_label_cap:
        labels[candidate.node].sort(key=lambda x: (x.objective, -x.voltage_pu, x.support_count))
        survivors = labels[candidate.node][: config.heuristic_label_cap]
        kept = candidate in survivors
        heuristic_removed = len(labels[candidate.node]) - len(survivors)
        labels[candidate.node] = survivors
        return kept, removed, heuristic_removed, 0
    return True, removed, 0, 0


def run_vamls(
    graph: GraphPU,
    source: int,
    target: int,
    support_specs: Dict[int, SupportSpec],
    config: VAMLSConfig,
    history_aware_dominance: bool = True,
) -> VAMLSResult:
    if source not in graph.nodes or target not in graph.nodes:
        raise ValueError("source and target must exist in graph")
    counters = _Counters()
    counters.max_active_labels = 1
    labels: Dict[int, List[Label]] = {}
    lookup: Dict[int, Label] = {}
    heap: List[Tuple[float, int]] = []
    labels[source] = []
    for start_voltage, start_supports, start_support_cost, used_support in apply_source_support_options(
        source, target, support_specs, config
    ):
        start = Label(
            label_id=next(counters.ids),
            node=source,
            objective=start_support_cost,
            active_loss_pu=0.0,
            reactive_loss_pu=0.0,
            voltage_pu=start_voltage,
            min_voltage_pu=start_voltage,
            support_count=len(start_supports),
            support_cost=start_support_cost,
            support_nodes=start_supports,
            visited_nodes=frozenset({source}),
            path=(source,),
            parent_label_id=None,
            min_pre_support_voltage_pu=config.nominal_voltage_pu,
        )
        labels[source].append(start)
        lookup[start.label_id] = start
        if used_support:
            counters.support_actions += 1
            counters.support_action_labels_generated += 1
        heapq.heappush(heap, (start.objective, start.label_id))
    while heap:
        _, label_id = heapq.heappop(heap)
        label = lookup[label_id]
        if label not in labels.get(label.node, []):
            continue
        counters.expanded += 1
        if label.node == target:
            continue
        for branch in graph.neighbors(label.node):
            counters.branches_evaluated += 1
            if branch.target in label.visited_nodes:
                counters.constraint += 1
                continue
            branch_result = evaluate_branch_pu(
                branch,
                label.voltage_pu,
                BranchPowerPU(config.p_transfer_pu, config.q_transfer_pu),
            )
            if branch_result.capacity_violation:
                counters.constraint += 1
                continue
            for voltage, support_nodes, support_cost, used_support in support_arrivals(
                branch.target,
                branch_result.arrival_voltage_pu,
                label.support_nodes,
                support_specs,
                config,
                source,
                target,
            ):
                min_operational_voltage = min(label.min_voltage_pu, voltage)
                min_pre_support_voltage = min(label.min_pre_support_voltage_pu, branch_result.arrival_voltage_pu)
                if voltage < config.voltage_lower_bound or voltage > config.voltage_upper_bound:
                    counters.constraint += 1
                    continue
                active_loss = label.active_loss_pu + branch_result.active_loss_pu
                reactive_loss = label.reactive_loss_pu + branch_result.reactive_loss_pu
                total_support_cost = label.support_cost + support_cost
                objective = active_loss + total_support_cost
                new_label = Label(
                    label_id=next(counters.ids),
                    node=branch.target,
                    objective=objective,
                    active_loss_pu=active_loss,
                    reactive_loss_pu=reactive_loss,
                    voltage_pu=voltage,
                    min_voltage_pu=min_operational_voltage,
                    support_count=len(support_nodes),
                    support_cost=total_support_cost,
                    support_nodes=support_nodes,
                    visited_nodes=label.visited_nodes | frozenset({branch.target}),
                    path=label.path + (branch.target,),
                    parent_label_id=label.label_id,
                    min_pre_support_voltage_pu=min_pre_support_voltage,
                )
                counters.generated += 1
                if used_support:
                    counters.support_actions += 1
                    counters.support_action_labels_generated += 1
                inserted, exact_removed, heuristic_removed, rejected_dominated = insert_label(labels, new_label, config, history_aware_dominance)
                counters.labels_dominated_by_exact_rule += exact_removed
                counters.labels_rejected_as_dominated += rejected_dominated
                counters.labels_removed_by_heuristic_cap += heuristic_removed
                counters.dominated += exact_removed + rejected_dominated
                counters.heuristic += heuristic_removed
                if not inserted:
                    continue
                lookup[new_label.label_id] = new_label
                if new_label in labels.get(new_label.node, []):
                    heapq.heappush(heap, (new_label.objective, new_label.label_id))
                else:
                    counters.labels_removed_by_heuristic_cap += 1
                    counters.heuristic += 1
                active_labels = sum(len(node_labels) for node_labels in labels.values())
                counters.max_active_labels = max(counters.max_active_labels, active_labels)
    best = min(labels.get(target, []), key=lambda x: (x.objective, -x.min_voltage_pu, x.support_count), default=None)
    violation = 0.0 if best else float("nan")
    if best:
        violation = max(0.0, config.voltage_lower_bound - best.min_voltage_pu)
    support_actions_in_best = len(best.support_nodes) if best else 0
    return VAMLSResult(
        feasible=best is not None,
        best_label=best,
        expanded_labels=counters.expanded,
        generated_labels=counters.generated,
        dominated_labels=counters.dominated,
        constraint_pruned_labels=counters.constraint,
        heuristic_pruned_labels=counters.heuristic,
        support_actions=counters.support_actions,
        voltage_violation_pu=violation,
        max_active_labels=counters.max_active_labels,
        branches_evaluated=counters.branches_evaluated,
        labels_dominated_by_exact_rule=counters.labels_dominated_by_exact_rule,
        labels_rejected_as_dominated=counters.labels_rejected_as_dominated,
        labels_removed_by_heuristic_cap=counters.labels_removed_by_heuristic_cap,
        support_action_labels_generated=counters.support_action_labels_generated,
        support_actions_in_best_solution=support_actions_in_best,
    )
