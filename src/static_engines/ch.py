"""Directed CH with bounded witness Dijkstra and recursive shortcut expansion.

Geisberger et al., WEA 2008, DOI 10.1007/978-3-540-68552-4_24.
The priority heuristic is a documented local choice, not the paper's tuned code.
"""

import heapq
import math
import time
from dataclasses import dataclass

from .common import BaseIndex, BuildBudget, Graph, deep_size, validate_order


@dataclass(frozen=True, slots=True)
class Arc:
    u: int
    v: int
    weight: float
    original_id: int = -1
    left: int = -1
    right: int = -1
    depth: int = 0


class CHIndex(BaseIndex):
    @classmethod
    def build(cls, edges, nodes, preprocessing_timeout_s=120, memory_cap_mb=1024,
              *, order=None):
        self = cls()
        self.stats = {
            "algorithm": "CH_PYTHON_WITNESS_CONTRACTION",
            "nodes_contracted": 0, "shortcuts_added": 0, "witness_searches": 0,
            "witnesses_found": 0, "witness_settled": 0, "max_shortcut_depth": 0,
            "ordering": "dynamic_degree_product_edge_difference_plus_contracted_neighbors"
                        if order is None else "explicit_order",
        }
        with BuildBudget(preprocessing_timeout_s, memory_cap_mb, self.stats) as budget:
            self.graph = Graph(edges, nodes, budget)
            n = len(self.graph.nodes)
            explicit = validate_order(self.graph, order, None)
            self.arcs = []
            outgoing, incoming = [dict() for _ in range(n)], [dict() for _ in range(n)]
            best_arc = {}
            for u, row in enumerate(self.graph.outgoing):
                for v, weight, original_id in row:
                    budget.check()
                    arc_id = len(self.arcs)
                    self.arcs.append(Arc(u, v, weight, original_id))
                    outgoing[u][v] = incoming[v][u] = best_arc[u, v] = arc_id
            self.rank = [-1] * n
            contracted_neighbors, versions = [0] * n, [0] * n

            def priority(v):
                a, b = len(incoming[v]), len(outgoing[v])
                return a * b - a - b + contracted_neighbors[v]

            priority_heap = [(priority(v), v, 0) for v in range(n)]
            heapq.heapify(priority_heap)
            for rank in range(n):
                budget.check(force=True)
                if explicit is None:
                    while True:
                        budget.check()
                        _, v, version = heapq.heappop(priority_heap)
                        if self.rank[v] == -1 and versions[v] == version:
                            break
                else:
                    v = explicit[rank]
                left_arcs = list(incoming[v].items())
                right_arcs = list(outgoing[v].items())
                candidates = []
                for u, left_id in left_arcs:
                    budget.check()
                    left = self.arcs[left_id]
                    bounds = {w: left.weight + self.arcs[right_id].weight
                              for w, right_id in right_arcs if u != w}
                    if not bounds:
                        continue
                    witness = self._witness(u, v, max(bounds.values()), outgoing, budget)
                    for w, right_id in right_arcs:
                        budget.check()
                        if u == w:
                            continue
                        distance = bounds[w]
                        if witness.get(w, math.inf) <= distance:
                            self.stats["witnesses_found"] += 1
                            continue
                        candidates.append((u, w, distance, left_id, right_id))
                # Insert only after all witness searches for v, so no witness
                # can depend on a newly inserted shortcut through v itself.
                for u, w, distance, left_id, right_id in candidates:
                    budget.check()
                    existing = outgoing[u].get(w)
                    if existing is not None and self.arcs[existing].weight <= distance:
                        continue
                    depth = 1 + max(self.arcs[left_id].depth, self.arcs[right_id].depth)
                    arc_id = len(self.arcs)
                    self.arcs.append(Arc(u, w, distance, -1, left_id, right_id, depth))
                    outgoing[u][w] = incoming[w][u] = best_arc[u, w] = arc_id
                    self.stats["shortcuts_added"] += 1
                    self.stats["max_shortcut_depth"] = max(
                        self.stats["max_shortcut_depth"], depth)
                neighbors = set(incoming[v]) | set(outgoing[v])
                for u in incoming[v]:
                    budget.check()
                    del outgoing[u][v]
                for w in outgoing[v]:
                    budget.check()
                    del incoming[w][v]
                incoming[v].clear()
                outgoing[v].clear()
                self.rank[v] = rank
                self.stats["nodes_contracted"] += 1
                for u in neighbors:
                    budget.check()
                    contracted_neighbors[u] += 1
                    versions[u] += 1
                    if explicit is None:
                        heapq.heappush(priority_heap, (priority(u), u, versions[u]))
            self.upward = [[] for _ in range(n)]
            self.backward_upward = [[] for _ in range(n)]
            for arc_id in best_arc.values():
                budget.check()
                arc = self.arcs[arc_id]
                if self.rank[arc.u] < self.rank[arc.v]:
                    self.upward[arc.u].append(arc_id)
                else:
                    self.backward_upward[arc.v].append(arc_id)
            self.arcs = tuple(self.arcs)
            self.rank = tuple(self.rank)
            self.upward = tuple(tuple(row) for row in self.upward)
            self.backward_upward = tuple(tuple(row) for row in self.backward_upward)
            self.stats.update(stored_arc_records=len(self.arcs),
                              query_upward_arcs=sum(map(len, self.upward)),
                              query_backward_upward_arcs=sum(map(len, self.backward_upward)))
            self.stats["hierarchy_memory_bytes"] = deep_size(
                (self.arcs, self.rank, self.upward, self.backward_upward), budget)
            self._finish_build(budget)
        self.stats["preprocessing_s"] = time.perf_counter() - budget.started
        return self

    def _witness(self, source, forbidden, bound, outgoing, budget):
        self.stats["witness_searches"] += 1
        distances, queue = {source: 0.0}, [(0.0, source)]
        while queue:
            budget.check()
            distance, u = heapq.heappop(queue)
            if distance != distances[u]:
                continue
            if distance > bound:
                break
            self.stats["witness_settled"] += 1
            for v, arc_id in outgoing[u].items():
                budget.check()
                if v == forbidden:
                    continue
                candidate = distance + self.arcs[arc_id].weight
                if candidate <= bound and candidate < distances.get(v, math.inf):
                    distances[v] = candidate
                    heapq.heappush(queue, (candidate, v))
        return distances

    def query(self, source, target, *, query_timeout_s=None, expected_graph_hash=None):
        s, t, started, budget = self._start_query(
            source, target, query_timeout_s, expected_graph_hash)
        query_started = time.perf_counter()
        best, meeting = (0.0, s) if s == t else (math.inf, None)
        forward, backward = {s: 0.0}, {t: 0.0}
        parents_f, parents_b = {}, {}
        queues = [[(0.0, s)], [(0.0, t)]]
        stats = {"forward_settled": 0, "backward_settled": 0, "relaxations": 0}
        # Each frontier must individually exceed the incumbent. The usual
        # sum-of-minima stopping rule is unsafe on CH's two restricted graphs.
        while queues[0] or queues[1]:
            budget.check()
            minimum_f = queues[0][0][0] if queues[0] else math.inf
            minimum_b = queues[1][0][0] if queues[1] else math.inf
            if minimum_f >= best and minimum_b >= best:
                break
            direction = 0 if minimum_f <= minimum_b else 1
            own, other = (forward, backward) if direction == 0 else (backward, forward)
            distance, u = heapq.heappop(queues[direction])
            if distance != own[u]:
                continue
            stats["forward_settled" if direction == 0 else "backward_settled"] += 1
            candidate = distance + other.get(u, math.inf)
            if candidate < best:
                best, meeting = candidate, u
            adjacency = self.upward[u] if direction == 0 else self.backward_upward[u]
            for arc_id in adjacency:
                budget.check()
                arc = self.arcs[arc_id]
                v = arc.v if direction == 0 else arc.u
                candidate = distance + arc.weight
                if candidate < own.get(v, math.inf):
                    own[v] = candidate
                    (parents_f if direction == 0 else parents_b)[v] = arc_id
                    heapq.heappush(queues[direction], (candidate, v))
                    stats["relaxations"] += 1
        budget.check(force=True)
        distance_s = time.perf_counter() - query_started
        reconstruction_started = time.perf_counter()
        contracted_path = []
        if meeting is not None:
            u = meeting
            while u != s:
                budget.check("reconstruction")
                arc_id = parents_f[u]
                contracted_path.append(arc_id)
                u = self.arcs[arc_id].u
            contracted_path.reverse()
            u = meeting
            while u != t:
                budget.check("reconstruction")
                arc_id = parents_b[u]
                contracted_path.append(arc_id)
                u = self.arcs[arc_id].v
        # Explicit stack implements recursive binary shortcut unpacking without
        # Python's recursion-depth limit; children always have smaller arc IDs.
        pending, edge_ids = list(reversed(contracted_path)), []
        while pending:
            budget.check("reconstruction")
            arc = self.arcs[pending.pop()]
            if arc.original_id >= 0:
                edge_ids.append(arc.original_id)
            else:
                pending.append(arc.right)
                pending.append(arc.left)
        stats["unpacked_original_edges"] = len(edge_ids)
        return self._result(s, t, best, edge_ids, started, distance_s,
                            reconstruction_started, budget, stats)


build = CHIndex.build
