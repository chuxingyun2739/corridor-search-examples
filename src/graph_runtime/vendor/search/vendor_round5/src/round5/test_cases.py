from __future__ import annotations

import random
from typing import Dict, Tuple

from .models import BranchPU, GraphPU, SupportSpec, build_undirected_graph
from .vamls import VAMLSConfig


def support_case_1() -> Tuple[str, GraphPU, int, int, Dict[int, SupportSpec], VAMLSConfig]:
    graph = build_undirected_graph([BranchPU(1, 2, 0.02, 0.01), BranchPU(2, 3, 0.02, 0.01)])
    return "case1_no_support_needed", graph, 1, 3, {2: SupportSpec(0.05, 0.02)}, VAMLSConfig(p_transfer_pu=0.20, q_transfer_pu=0.05, max_support_nodes=1)


def support_case_2() -> Tuple[str, GraphPU, int, int, Dict[int, SupportSpec], VAMLSConfig]:
    graph = build_undirected_graph([BranchPU(1, 2, 0.12, 0.04), BranchPU(2, 3, 0.08, 0.03)])
    return "case2_one_support_required", graph, 1, 3, {2: SupportSpec(0.12, 0.01)}, VAMLSConfig(p_transfer_pu=0.55, q_transfer_pu=0.12, max_support_nodes=1)


def support_case_3() -> Tuple[str, GraphPU, int, int, Dict[int, SupportSpec], VAMLSConfig]:
    graph = build_undirected_graph(
        [
            BranchPU(1, 2, 0.09, 0.03),
            BranchPU(2, 4, 0.06, 0.02),
            BranchPU(1, 3, 0.08, 0.025),
            BranchPU(3, 4, 0.07, 0.02),
        ]
    )
    supports = {2: SupportSpec(0.20, 0.08), 3: SupportSpec(0.12, 0.01)}
    return "case3_support_tradeoff", graph, 1, 4, supports, VAMLSConfig(p_transfer_pu=0.70, q_transfer_pu=0.15, max_support_nodes=1)


def synthetic_case(n: int) -> Tuple[str, GraphPU, int, int, Dict[int, SupportSpec], VAMLSConfig]:
    branches = []
    for i in range(1, n):
        branches.append(BranchPU(i, i + 1, 0.025 + 0.002 * (i % 3), 0.01))
    for i in range(1, n - 2):
        branches.append(BranchPU(i, i + 2, 0.045 + 0.002 * (i % 2), 0.012))
    supports = {i: SupportSpec(0.08, 0.02 + 0.005 * (i % 2)) for i in range(2, n) if i % 3 == 0}
    return f"synthetic_{n}_node", build_undirected_graph(branches), 1, n, supports, VAMLSConfig(p_transfer_pu=0.30, q_transfer_pu=0.08, max_support_nodes=2)


def random_case(index: int, n: int = 8) -> Tuple[str, GraphPU, int, int, Dict[int, SupportSpec], VAMLSConfig]:
    rng = random.Random(20260616 + index)
    branches = [BranchPU(i, i + 1, rng.uniform(0.015, 0.05), rng.uniform(0.005, 0.02)) for i in range(1, n)]
    for i in range(1, n - 1):
        if rng.random() < 0.45:
            branches.append(BranchPU(i, min(n, i + rng.randint(2, 3)), rng.uniform(0.02, 0.07), rng.uniform(0.005, 0.025)))
    supports = {i: SupportSpec(rng.uniform(0.04, 0.12), rng.uniform(0.005, 0.04)) for i in range(2, n) if rng.random() < 0.35}
    return f"random_{index:02d}", build_undirected_graph(branches), 1, n, supports, VAMLSConfig(p_transfer_pu=rng.uniform(0.18, 0.42), q_transfer_pu=rng.uniform(0.03, 0.12), max_support_nodes=2)


def dominance_counterexample_case() -> Tuple[str, GraphPU, int, int, Dict[int, SupportSpec], VAMLSConfig]:
    graph = GraphPU(
        {
            1: [BranchPU(1, 4, 0.020, 0.002), BranchPU(1, 2, 0.060, 0.002)],
            2: [BranchPU(2, 3, 0.060, 0.002)],
            3: [BranchPU(3, 4, 0.005, 0.002)],
            4: [BranchPU(4, 3, 0.005, 0.002), BranchPU(4, 5, 0.060, 0.010)],
            5: [],
        }
    )
    supports = {3: SupportSpec(0.20, 0.0)}
    config = VAMLSConfig(
        p_transfer_pu=1.00,
        q_transfer_pu=0.05,
        voltage_lower_bound=0.92,
        voltage_upper_bound=1.10,
        max_support_nodes=1,
    )
    return "path_history_dominance_counterexample", graph, 1, 5, supports, config
