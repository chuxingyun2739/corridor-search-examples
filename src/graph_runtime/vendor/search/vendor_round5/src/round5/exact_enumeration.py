from __future__ import annotations

import itertools
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from .models import GraphPU, SupportSpec, edge_lookup
from .power_flow_approximation import BranchPowerPU, downstream_accumulated_load, evaluate_branch_pu
from .vamls import VAMLSConfig, is_support_action_allowed, support_arrivals


@dataclass(frozen=True)
class ExactSolution:
    feasible: bool
    path: Tuple[int, ...]
    support_nodes: Tuple[int, ...]
    objective: float
    active_loss_pu: float
    reactive_loss_pu: float
    min_voltage_pu: float
    min_pre_support_voltage_pu: float
    terminal_voltage_pu: float
    combinations_evaluated: int
    runtime_seconds: float


def enumerate_simple_paths(graph: GraphPU, source: int, target: int, max_depth: int = 12) -> List[Tuple[int, ...]]:
    paths: List[Tuple[int, ...]] = []

    def visit(node: int, path: List[int]) -> None:
        if len(path) > max_depth:
            return
        if node == target:
            paths.append(tuple(path))
            return
        for branch in graph.neighbors(node):
            if branch.target not in path:
                visit(branch.target, path + [branch.target])

    visit(source, [source])
    return paths


def support_combinations(
    path: Tuple[int, ...],
    support_specs: Dict[int, SupportSpec],
    max_count: int,
    config: Optional[VAMLSConfig] = None,
) -> Iterable[Tuple[int, ...]]:
    if config is None:
        candidates = [node for node in path[1:-1] if node in support_specs and support_specs[node].available]
    else:
        source, target = path[0], path[-1]
        candidates = [
            node
            for node in path
            if node in support_specs
            and support_specs[node].available
            and is_support_action_allowed(node, source, target, config)
        ]
    for r in range(min(max_count, len(candidates)) + 1):
        yield from itertools.combinations(candidates, r)


def evaluate_path_with_supports(
    graph: GraphPU,
    path: Tuple[int, ...],
    chosen_supports: Tuple[int, ...],
    support_specs: Dict[int, SupportSpec],
    config: VAMLSConfig,
    power_model: str = "fixed_transfer",
) -> Optional[ExactSolution]:
    lookup = edge_lookup(graph)
    voltage = config.nominal_voltage_pu
    min_operational_voltage = voltage
    min_pre_support_voltage = voltage
    active_loss = 0.0
    reactive_loss = 0.0
    support_cost = 0.0
    powers = {}
    if path[0] in chosen_supports:
        if not is_support_action_allowed(path[0], path[0], path[-1], config):
            return None
        spec = support_specs[path[0]]
        supported = min(config.nominal_voltage_pu, voltage + spec.capacity_pu)
        used = max(0.0, supported - voltage)
        voltage = supported
        min_operational_voltage = min(min_operational_voltage, voltage)
        support_cost += config.lambda_support_count + spec.fixed_cost + config.lambda_support_capacity * used + spec.unit_cost * used
    if power_model == "downstream_accumulated_load":
        # Downstream load values must be precomputed externally for full use; for round2
        # validation, fixed_transfer is the main model.
        powers = {}
    for u, v in zip(path, path[1:]):
        branch = lookup[(u, v)]
        branch_power = powers.get((u, v), BranchPowerPU(config.p_transfer_pu, config.q_transfer_pu))
        result = evaluate_branch_pu(branch, voltage, branch_power)
        if result.capacity_violation:
            return None
        raw_voltage = result.arrival_voltage_pu
        voltage = raw_voltage
        if v in chosen_supports:
            if not is_support_action_allowed(v, path[0], path[-1], config):
                return None
            spec = support_specs[v]
            voltage = min(config.nominal_voltage_pu, raw_voltage + spec.capacity_pu)
            support_cost += config.lambda_support_count + spec.fixed_cost + config.lambda_support_capacity * max(0.0, voltage - raw_voltage) + spec.unit_cost * max(0.0, voltage - raw_voltage)
        min_pre_support_voltage = min(min_pre_support_voltage, raw_voltage)
        min_operational_voltage = min(min_operational_voltage, voltage)
        if voltage < config.voltage_lower_bound or voltage > config.voltage_upper_bound:
            return None
        active_loss += result.active_loss_pu
        reactive_loss += result.reactive_loss_pu
    return ExactSolution(
        feasible=True,
        path=path,
        support_nodes=tuple(sorted(chosen_supports)),
        objective=active_loss + support_cost,
        active_loss_pu=active_loss,
        reactive_loss_pu=reactive_loss,
        min_voltage_pu=min_operational_voltage,
        min_pre_support_voltage_pu=min_pre_support_voltage,
        terminal_voltage_pu=voltage,
        combinations_evaluated=1,
        runtime_seconds=0.0,
    )


def exact_enumeration(
    graph: GraphPU,
    source: int,
    target: int,
    support_specs: Dict[int, SupportSpec],
    config: VAMLSConfig,
    max_depth: int = 12,
) -> ExactSolution:
    start = time.perf_counter()
    best: Optional[ExactSolution] = None
    count = 0
    for path in enumerate_simple_paths(graph, source, target, max_depth=max_depth):
        for supports in support_combinations(path, support_specs, config.max_support_nodes, config):
            count += 1
            solution = evaluate_path_with_supports(graph, path, supports, support_specs, config)
            if solution and (best is None or solution.objective < best.objective):
                best = solution
    elapsed = time.perf_counter() - start
    if best is None:
        return ExactSolution(False, (), (), float("inf"), float("inf"), float("inf"), float("nan"), float("nan"), float("nan"), count, elapsed)
    return ExactSolution(
        best.feasible,
        best.path,
        best.support_nodes,
        best.objective,
        best.active_loss_pu,
        best.reactive_loss_pu,
        best.min_voltage_pu,
        best.min_pre_support_voltage_pu,
        best.terminal_voltage_pu,
        count,
        elapsed,
    )

