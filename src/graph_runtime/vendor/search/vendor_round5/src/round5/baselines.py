from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .exact_enumeration import evaluate_path_with_supports, support_combinations
from .models import GraphPU, SupportSpec
from .power_flow_approximation import BranchPowerPU, evaluate_branch_pu
from .vamls import Label, VAMLSConfig, VAMLSResult, apply_source_support_options, support_arrivals


@dataclass
class PathEvalResult:
    feasible: bool
    path: Tuple[int, ...]
    support_nodes: Tuple[int, ...]
    objective: float
    min_voltage_pu: float
    active_loss_pu: float
    reactive_loss_pu: float = 0.0
    support_cost: float = 0.0
    min_pre_support_voltage_pu: float = float("nan")
    runtime_seconds: float = 0.0
    expanded_labels: int = 0
    generated_labels: int = 0
    branches_evaluated: int = 0


def impedance_weighted_dijkstra(graph: GraphPU, source: int, target: int) -> Tuple[float, Tuple[int, ...], int]:
    dist = {source: 0.0}
    prev: Dict[int, Optional[int]] = {source: None}
    heap = [(0.0, source)]
    expanded = 0
    while heap:
        cost, node = heapq.heappop(heap)
        if cost != dist.get(node):
            continue
        expanded += 1
        if node == target:
            break
        for branch in graph.neighbors(node):
            alt = cost + (branch.r_pu**2 + branch.x_pu**2) ** 0.5
            if alt < dist.get(branch.target, float("inf")):
                dist[branch.target] = alt
                prev[branch.target] = node
                heapq.heappush(heap, (alt, branch.target))
    if target not in dist:
        return float("inf"), (), expanded
    path = []
    cur: Optional[int] = target
    while cur is not None:
        path.append(cur)
        cur = prev[cur]
    return dist[target], tuple(reversed(path)), expanded


def impedance_dijkstra_post_eval(
    graph: GraphPU,
    source: int,
    target: int,
    support_specs: Dict[int, SupportSpec],
    config: VAMLSConfig,
) -> PathEvalResult:
    _, path, expanded = impedance_weighted_dijkstra(graph, source, target)
    if not path:
        return PathEvalResult(False, (), (), float("inf"), float("nan"), float("inf"), expanded_labels=expanded)
    best = None
    for supports in support_combinations(path, support_specs, config.max_support_nodes, config):
        solution = evaluate_path_with_supports(graph, path, supports, support_specs, config)
        if solution and (best is None or solution.objective < best.objective):
            best = solution
    if best is None:
        return PathEvalResult(False, path, (), float("inf"), float("nan"), float("inf"), expanded_labels=expanded)
    return PathEvalResult(
        True,
        best.path,
        best.support_nodes,
        best.objective,
        best.min_voltage_pu,
        best.active_loss_pu,
        best.reactive_loss_pu,
        best.objective - best.active_loss_pu,
        best.min_pre_support_voltage_pu,
        expanded_labels=expanded,
    )


def state_augmented_dijkstra(
    graph: GraphPU,
    source: int,
    target: int,
    support_specs: Dict[int, SupportSpec],
    config: VAMLSConfig,
    voltage_decimals: int = 4,
) -> VAMLSResult:
    """Independent state Dijkstra with discretized voltage and support decisions."""
    dist = {}
    heap = []
    for start_voltage, start_supports, start_support_cost, used_support in apply_source_support_options(
        source, target, support_specs, config
    ):
        start = (
            source,
            round(start_voltage, voltage_decimals),
            0.0,
            0.0,
            start_support_cost,
            start_voltage,
            config.nominal_voltage_pu,
            start_supports,
            frozenset({source}),
            (source,),
        )
        dist[start] = start_support_cost
        heapq.heappush(heap, (start_support_cost, start))
    best_label = None
    expanded = generated = constraint = support_actions = branches = 0
    label_id = itertools.count()
    while heap:
        cost, state = heapq.heappop(heap)
        if cost != dist.get(state):
            continue
        node, voltage, active_loss, reactive_loss, support_cost_total, min_operational_voltage, min_pre_support_voltage, support_nodes, visited, path = state
        expanded += 1
        if node == target:
            best_label = Label(
                next(label_id),
                node,
                cost,
                active_loss,
                reactive_loss,
                voltage,
                min_operational_voltage,
                len(support_nodes),
                support_cost_total,
                support_nodes,
                visited,
                path,
                None,
                min_pre_support_voltage,
            )
            break
        for branch in graph.neighbors(node):
            branches += 1
            if branch.target in visited:
                constraint += 1
                continue
            br = evaluate_branch_pu(branch, voltage, BranchPowerPU(config.p_transfer_pu, config.q_transfer_pu))
            for new_voltage, new_supports, support_cost, used_support in support_arrivals(
                branch.target, br.arrival_voltage_pu, support_nodes, support_specs, config, source, target
            ):
                if new_voltage < config.voltage_lower_bound or new_voltage > config.voltage_upper_bound or br.capacity_violation:
                    constraint += 1
                    continue
                generated += 1
                new_cost = cost + br.active_loss_pu + support_cost
                new_state = (
                    branch.target,
                    round(new_voltage, voltage_decimals),
                    active_loss + br.active_loss_pu,
                    reactive_loss + br.reactive_loss_pu,
                    support_cost_total + support_cost,
                    min(min_operational_voltage, new_voltage),
                    min(min_pre_support_voltage, br.arrival_voltage_pu),
                    new_supports,
                    visited | frozenset({branch.target}),
                    path + (branch.target,),
                )
                if new_cost < dist.get(new_state, float("inf")):
                    if used_support:
                        support_actions += 1
                    dist[new_state] = new_cost
                    heapq.heappush(heap, (new_cost, new_state))
    feasible = best_label is not None
    return VAMLSResult(feasible, best_label, expanded, generated, 0, constraint, 0, support_actions, 0.0, len(dist), branches)


def no_dominance_elementary_label_search(
    graph: GraphPU,
    source: int,
    target: int,
    support_specs: Dict[int, SupportSpec],
    config: VAMLSConfig,
) -> VAMLSResult:
    """Independent elementary label search with no VAMLS dominance compression."""
    labels: Dict[Tuple[int, Tuple[int, ...], Tuple[int, ...]], Label] = {}
    heap: List[Tuple[float, int, Label]] = []
    ids = itertools.count()
    for start_voltage, start_supports, start_support_cost, used_support in apply_source_support_options(
        source, target, support_specs, config
    ):
        start = Label(next(ids), source, start_support_cost, 0.0, 0.0, start_voltage, start_voltage, len(start_supports), start_support_cost, start_supports, frozenset({source}), (source,), None, config.nominal_voltage_pu)
        labels[(source, start.path, start.support_nodes)] = start
        heapq.heappush(heap, (start.objective, start.label_id, start))
    expanded = generated = duplicates = constraint = support_actions = branches = max_active = 0
    while heap:
        _, _, label = heapq.heappop(heap)
        if labels.get((label.node, label.path, label.support_nodes)) is not label:
            continue
        expanded += 1
        if label.node == target:
            continue
        for branch in graph.neighbors(label.node):
            branches += 1
            if branch.target in label.visited_nodes:
                constraint += 1
                continue
            br = evaluate_branch_pu(branch, label.voltage_pu, BranchPowerPU(config.p_transfer_pu, config.q_transfer_pu))
            for voltage, supports, support_cost, used_support in support_arrivals(
                branch.target, br.arrival_voltage_pu, label.support_nodes, support_specs, config, source, target
            ):
                if voltage < config.voltage_lower_bound or voltage > config.voltage_upper_bound or br.capacity_violation:
                    constraint += 1
                    continue
                candidate = Label(
                    next(ids),
                    branch.target,
                    label.active_loss_pu + br.active_loss_pu + label.support_cost + support_cost,
                    label.active_loss_pu + br.active_loss_pu,
                    label.reactive_loss_pu + br.reactive_loss_pu,
                    voltage,
                    min(label.min_voltage_pu, voltage),
                    len(supports),
                    label.support_cost + support_cost,
                    supports,
                    label.visited_nodes | frozenset({branch.target}),
                    label.path + (branch.target,),
                    label.label_id,
                    min(label.min_pre_support_voltage_pu, br.arrival_voltage_pu),
                )
                generated += 1
                key = (candidate.node, candidate.path, candidate.support_nodes)
                if key in labels and labels[key].objective <= candidate.objective + config.dominance_eps:
                    duplicates += 1
                    continue
                labels[key] = candidate
                if used_support:
                    support_actions += 1
                max_active = max(max_active, len(labels))
                heapq.heappush(heap, (candidate.objective, candidate.label_id, candidate))
    best = min((label for (node, _, _), label in labels.items() if node == target), key=lambda x: x.objective, default=None)
    return VAMLSResult(best is not None, best, expanded, generated, duplicates, constraint, 0, support_actions, 0.0, max_active, branches)


def enumerated_k_lowest_impedance_simple_paths(
    graph: GraphPU,
    source: int,
    target: int,
    support_specs: Dict[int, SupportSpec],
    config: VAMLSConfig,
    k: int = 10,
    max_depth: int = 12,
) -> PathEvalResult:
    paths: List[Tuple[float, Tuple[int, ...]]] = []

    def visit(node: int, path: Tuple[int, ...], cost: float) -> None:
        if len(path) > max_depth:
            return
        if node == target:
            paths.append((cost, path))
            return
        for branch in graph.neighbors(node):
            if branch.target not in path:
                visit(branch.target, path + (branch.target,), cost + (branch.r_pu**2 + branch.x_pu**2) ** 0.5)

    visit(source, (source,), 0.0)
    best = None
    for _, path in sorted(paths, key=lambda x: x[0])[:k]:
        for supports in support_combinations(path, support_specs, config.max_support_nodes, config):
            solution = evaluate_path_with_supports(graph, path, supports, support_specs, config)
            if solution and (best is None or solution.objective < best.objective):
                best = solution
    if best is None:
        return PathEvalResult(False, (), (), float("inf"), float("nan"), float("inf"), expanded_labels=min(k, len(paths)))
    return PathEvalResult(
        True,
        best.path,
        best.support_nodes,
        best.objective,
        best.min_voltage_pu,
        best.active_loss_pu,
        best.reactive_loss_pu,
        best.objective - best.active_loss_pu,
        best.min_pre_support_voltage_pu,
        expanded_labels=min(k, len(paths)),
    )


def conventional_multilabel_dijkstra(*args, **kwargs):
    return no_dominance_elementary_label_search(*args, **kwargs)




def vamls_accelerated(graph: GraphPU, source: int, target: int, support_specs: Dict[int, SupportSpec], config: VAMLSConfig, label_cap: int = 4):
    from .vamls import run_vamls

    cfg = VAMLSConfig(**{**config.__dict__, "heuristic_label_cap": label_cap})
    return run_vamls(graph, source, target, support_specs, cfg, history_aware_dominance=True)
