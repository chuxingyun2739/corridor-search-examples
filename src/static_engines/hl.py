"""Weighted directed pruned landmark 2-hop labels with original-edge pointers.

Akiba, Iwata and Yoshida, SIGMOD 2013, DOI 10.1145/2463676.2465315,
Algorithms 1-2 and Section 6. No bit-parallel unweighted labeling is used.
"""

import heapq
import math
import time
from dataclasses import dataclass

from .common import BaseIndex, BuildBudget, Graph, deep_size, validate_order


@dataclass(frozen=True, slots=True)
class Label:
    distance: float
    parent: int
    edge_id: int


def intersect(left, right, budget=None):
    if len(left) > len(right):
        left, right = right, left
    best, hub = math.inf, None
    for h, entry in left.items():
        if budget is not None:
            budget.check()
        other = right.get(h)
        if other is not None:
            candidate = entry.distance + other.distance
            if candidate < best:
                best, hub = candidate, h
    return best, hub


class HubLabelIndex(BaseIndex):
    @classmethod
    def build(cls, edges, nodes, preprocessing_timeout_s=120, memory_cap_mb=1024,
              *, order=None):
        self = cls()
        self.stats = {
            "algorithm": "HL_PLL_WEIGHTED_DIRECTED", "hubs_processed": 0,
            "pruned_vertices": 0, "dijkstra_settled": 0, "relaxations": 0,
            "ordering": "descending_total_degree" if order is None else "explicit_order",
        }
        with BuildBudget(preprocessing_timeout_s, memory_cap_mb, self.stats) as budget:
            self.graph = Graph(edges, nodes, budget)
            n = len(self.graph.nodes)
            default = sorted(range(n), key=lambda v: (
                -len(self.graph.outgoing[v]) - len(self.graph.incoming[v]), v))
            self.order = tuple(validate_order(self.graph, order, default))
            self.out_labels = [dict() for _ in range(n)]
            self.in_labels = [dict() for _ in range(n)]
            for hub in self.order:
                budget.check(force=True)
                # Only earlier hubs may witness pruning in either direction.
                root_out = dict(self.out_labels[hub])
                root_in = dict(self.in_labels[hub])
                self._pruned_dijkstra(hub, False, root_out, budget)
                self._pruned_dijkstra(hub, True, root_in, budget)
                self.stats["hubs_processed"] += 1
            self.out_labels = tuple(self.out_labels)
            self.in_labels = tuple(self.in_labels)
            out_sizes, in_sizes = list(map(len, self.out_labels)), list(map(len, self.in_labels))
            total_out, total_in = sum(out_sizes), sum(in_sizes)
            self.stats.update(
                forward_label_entries=total_out, backward_label_entries=total_in,
                total_label_entries=total_out + total_in,
                max_forward_label_size=max(out_sizes, default=0),
                max_backward_label_size=max(in_sizes, default=0),
                max_label_size=max(out_sizes + in_sizes, default=0),
                mean_forward_label_size=total_out / n if n else 0.0,
                mean_backward_label_size=total_in / n if n else 0.0,
            )
            self.stats["label_memory_bytes"] = deep_size(
                (self.out_labels, self.in_labels), budget)
            self._finish_build(budget)
        self.stats["preprocessing_s"] = time.perf_counter() - budget.started
        return self

    def _pruned_dijkstra(self, hub, reverse, root_labels, budget):
        adjacency = self.graph.incoming if reverse else self.graph.outgoing
        labels = self.out_labels if reverse else self.in_labels
        queue = [(0.0, hub)]
        distances, parents, settled = {hub: 0.0}, {hub: (hub, -1)}, set()
        while queue:
            budget.check()
            distance, u = heapq.heappop(queue)
            if u in settled or distance != distances[u]:
                continue
            settled.add(u)
            self.stats["dijkstra_settled"] += 1
            covered, _ = intersect(root_labels, labels[u], budget)
            if covered <= distance:
                self.stats["pruned_vertices"] += 1
                continue
            parent, edge_id = parents[u]
            labels[u][hub] = Label(distance, parent, edge_id)
            for v, weight, original_id in adjacency[u]:
                budget.check()
                candidate = distance + weight
                if v not in settled and candidate < distances.get(v, math.inf):
                    distances[v] = candidate
                    parents[v] = (u, original_id)
                    heapq.heappush(queue, (candidate, v))
                    self.stats["relaxations"] += 1

    def label_distance(self, source, target):
        """Pure two-hop intersection, including self-pair coverage (no search)."""
        s, t = self.graph.node_index[source], self.graph.node_index[target]
        return intersect(self.out_labels[s], self.in_labels[t])[0]

    def query(self, source, target, *, query_timeout_s=None, expected_graph_hash=None):
        s, t, started, budget = self._start_query(
            source, target, query_timeout_s, expected_graph_hash)
        query_started = time.perf_counter()
        distance, hub = intersect(self.out_labels[s], self.in_labels[t], budget)
        budget.check(force=True)
        distance_s = time.perf_counter() - query_started
        reconstruction_started = time.perf_counter()
        edge_ids = []
        if hub is not None and s != t:
            u, steps = s, 0
            while u != hub:
                budget.check("reconstruction")
                entry = self.out_labels[u][hub]
                edge_ids.append(entry.edge_id)
                u = entry.parent
                steps += 1
                if steps > len(self.graph.nodes):
                    raise RuntimeError("out-label parent cycle")
            u, suffix, steps = t, [], 0
            while u != hub:
                budget.check("reconstruction")
                entry = self.in_labels[u][hub]
                suffix.append(entry.edge_id)
                u = entry.parent
                steps += 1
                if steps > len(self.graph.nodes):
                    raise RuntimeError("in-label parent cycle")
            edge_ids.extend(reversed(suffix))
        stats = {"labels_scanned": min(len(self.out_labels[s]), len(self.in_labels[t])),
                 "meeting_hub": None if hub is None else self.graph.nodes[hub],
                 "pointer_edges": len(edge_ids)}
        return self._result(s, t, distance, edge_ids, started, distance_s,
                            reconstruction_started, budget, stats)


build = HubLabelIndex.build
