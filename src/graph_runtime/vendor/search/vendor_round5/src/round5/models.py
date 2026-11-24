from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class LoadPU:
    p_pu: float = 0.0
    q_pu: float = 0.0


@dataclass(frozen=True)
class BranchPU:
    source: int
    target: int
    r_pu: float
    x_pu: float
    rate_pu: Optional[float] = None


@dataclass(frozen=True)
class SupportSpec:
    capacity_pu: float
    fixed_cost: float
    unit_cost: float = 0.0
    available: bool = True


@dataclass(frozen=True)
class GraphPU:
    adjacency: Dict[int, List[BranchPU]]

    @property
    def nodes(self) -> set[int]:
        nodes = set(self.adjacency)
        for branches in self.adjacency.values():
            for branch in branches:
                nodes.add(branch.target)
        return nodes

    def neighbors(self, node: int) -> List[BranchPU]:
        return self.adjacency.get(node, [])


def build_undirected_graph(branches: Iterable[BranchPU]) -> GraphPU:
    adjacency: Dict[int, List[BranchPU]] = {}
    for branch in branches:
        if branch.r_pu < 0 or branch.x_pu < 0:
            raise ValueError("branch r_pu and x_pu must be non-negative")
        adjacency.setdefault(branch.source, []).append(branch)
        adjacency.setdefault(branch.target, []).append(
            BranchPU(branch.target, branch.source, branch.r_pu, branch.x_pu, branch.rate_pu)
        )
    return GraphPU(adjacency)


def edge_lookup(graph: GraphPU) -> Dict[Tuple[int, int], BranchPU]:
    return {(branch.source, branch.target): branch for branches in graph.adjacency.values() for branch in branches}

