"""Input identity, cooperative budgets and original-edge reconstruction."""

import hashlib
import json
import math
import sys
import time
import tracemalloc


class GraphMismatch(ValueError):
    """An index was offered a different topology or weight instance."""


class BudgetExceeded(RuntimeError):
    def __init__(self, status, phase, reason, stats):
        super().__init__(f"{status} during {phase}: {reason}")
        self.status = status
        self.phase = phase
        self.reason = reason
        self.stats = dict(stats, status=status, phase=phase, reason=reason)


def _budget_number(value, name):
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and nonnegative")
    return value


class BuildBudget:
    """Cooperative incremental Python-heap cap, not a process RSS limiter."""

    def __init__(self, seconds, memory_mb, stats):
        self.seconds = _budget_number(seconds, "preprocessing_timeout_s")
        self.cap = _budget_number(memory_mb, "memory_cap_mb") * 1024 * 1024
        self.stats = stats
        self.started = time.perf_counter()
        self.owns_trace = False
        self.baseline = 0
        self.peak = 0
        self.steps = 0

    def __enter__(self):
        self.owns_trace = not tracemalloc.is_tracing()
        if self.owns_trace:
            tracemalloc.start()
        self.baseline = tracemalloc.get_traced_memory()[0]
        self.stats["memory_accounting"] = (
            "incremental_tracemalloc_peak" if self.owns_trace
            else "incremental_tracemalloc_current_samples_external_tracer")
        try:
            self.check(force=True)
        except BaseException:
            if self.owns_trace:
                tracemalloc.stop()
            raise
        return self

    def check(self, force=False):
        self.steps += 1
        if not force and self.steps % 64:
            return
        current, peak = tracemalloc.get_traced_memory()
        allocated = max(0, current - self.baseline)
        if self.owns_trace:
            allocated = max(allocated, peak - self.baseline)
        self.peak = max(self.peak, allocated)
        elapsed = time.perf_counter() - self.started
        self.stats.update(elapsed_s=elapsed, build_peak_traced_bytes=self.peak,
                          memory_cap_bytes=int(self.cap),
                          preprocessing_timeout_s=self.seconds)
        if self.cap == 0 or self.peak > self.cap:
            raise BudgetExceeded("RESOURCE_LIMIT", "preprocessing",
                                 "incremental traced Python memory cap exceeded", self.stats)
        if elapsed >= self.seconds:
            raise BudgetExceeded("TIMEOUT", "preprocessing",
                                 "preprocessing wall-clock deadline exceeded", self.stats)

    def __exit__(self, exc_type, exc, tb):
        if self.owns_trace:
            tracemalloc.stop()
        if exc_type is MemoryError:
            self.stats["elapsed_s"] = time.perf_counter() - self.started
            raise BudgetExceeded("RESOURCE_LIMIT", "preprocessing",
                                 "Python allocation failed", self.stats) from exc


class QueryBudget:
    def __init__(self, seconds, started):
        self.started = started
        self.deadline = (math.inf if seconds is None else
                         started + _budget_number(seconds, "query_timeout_s"))
        self.steps = 0

    def check(self, phase="distance_query", force=False):
        if self.deadline == math.inf:
            return
        self.steps += 1
        if (force or self.steps % 64 == 0) and time.perf_counter() >= self.deadline:
            raise BudgetExceeded("TIMEOUT", phase, "query wall-clock deadline exceeded",
                                 {"elapsed_s": time.perf_counter() - self.started})


def _node_token(node):
    if node is None:
        return ["none"]
    if type(node) is bool:
        return ["bool", node]
    if type(node) is int:
        return ["int", str(node)]
    if type(node) is str:
        return ["str", node]
    if type(node) is bytes:
        return ["bytes", node.hex()]
    if type(node) is float and math.isfinite(node):
        return ["float", (0.0 if node == 0 else node).hex()]
    if type(node) is tuple:
        return ["tuple", [_node_token(x) for x in node]]
    raise ValueError("unsupported node ID; use built-in scalars or tuples of them")


def _token(node):
    return json.dumps(_node_token(node), ensure_ascii=True, separators=(",", ":"))


class Graph:
    def __init__(self, edges, nodes, budget=None):
        def check():
            if budget is not None:
                budget.check()

        identities = {}
        for node in nodes:
            check()
            token = _token(node)
            if node in identities and identities[node] != token:
                raise ValueError("node IDs with different types compare equal")
            identities[node] = token
        self.nodes = tuple(sorted(identities, key=identities.__getitem__))
        self.node_index = {node: i for i, node in enumerate(self.nodes)}
        raw = []
        minimum = {}
        max_weight = 0.0
        for edge_id, triple in enumerate(edges):
            check()
            u, v, weight = triple
            if u not in identities or v not in identities:
                raise ValueError("every edge endpoint must occur in nodes")
            if _token(u) != identities[u] or _token(v) != identities[v]:
                raise ValueError("edge endpoint type does not match node identity")
            w = float(weight)
            if not math.isfinite(w) or w < 0:
                raise ValueError("edge weights must be finite and nonnegative")
            w = 0.0 if w == 0 else w
            max_weight = max(max_weight, w)
            a, b = self.node_index[u], self.node_index[v]
            raw.append((a, b, w))
            old = minimum.get((a, b))
            if old is None or w < old[0]:
                minimum[a, b] = (w, edge_id)
        if not math.isfinite(max_weight * max(1, len(self.nodes))):
            raise ValueError("weight scale may overflow finite path sums; rescale weights")
        self.original_edges = tuple(raw)
        self.outgoing = [[] for _ in self.nodes]
        self.incoming = [[] for _ in self.nodes]
        for (a, b), (w, edge_id) in sorted(minimum.items()):
            check()
            if a != b:
                self.outgoing[a].append((b, w, edge_id))
                self.incoming[b].append((a, w, edge_id))
        self.outgoing = tuple(tuple(row) for row in self.outgoing)
        self.incoming = tuple(tuple(row) for row in self.incoming)
        self.edge_count = sum(len(row) for row in self.outgoing)
        digest = hashlib.sha256(b"static-engine-directed-input-v1\n")
        for node in self.nodes:
            check()
            digest.update((identities[node] + "\n").encode("ascii"))
        digest.update(b"EDGES\n")
        for a, b, w in sorted(raw):
            check()
            digest.update(f"{a},{b},{w.hex()}\n".encode("ascii"))
        self.graph_hash = digest.hexdigest()


def graph_hash(edges, nodes):
    """Canonical graph identity, including isolates and every supplied arc."""
    return Graph(edges, nodes).graph_hash


def deep_size(value, budget=None):
    """Reachable Python object footprint, counted once per object identity."""
    stack, seen, total = [value], set(), 0
    while stack:
        if budget is not None:
            budget.check()
        obj = stack.pop()
        identity = id(obj)
        if identity in seen:
            continue
        seen.add(identity)
        total += sys.getsizeof(obj)
        if isinstance(obj, dict):
            stack.extend(obj.keys())
            stack.extend(obj.values())
        elif isinstance(obj, (tuple, list, set, frozenset)):
            stack.extend(obj)
        elif hasattr(obj, "__dict__"):
            stack.append(vars(obj))
        elif hasattr(type(obj), "__slots__"):
            stack.extend(getattr(obj, name) for name in type(obj).__slots__
                         if hasattr(obj, name))
    return total


def finish_original_path(graph, source, target, edge_ids, distance, budget):
    """Expand node IDs and erase repeated-vertex zero-cost shortest-path walks."""
    if math.isinf(distance):
        return [], [], math.inf
    vertices, selected, positions = [source], [], {source: 0}
    for edge_id in edge_ids:
        budget.check("reconstruction")
        u, v, _ = graph.original_edges[edge_id]
        if vertices[-1] != u:
            raise RuntimeError("original-edge reconstruction is not contiguous")
        if v in positions:
            cut = positions[v]
            for old in vertices[cut + 1:]:
                budget.check("reconstruction")
                del positions[old]
            del vertices[cut + 1:]
            del selected[cut:]
        else:
            selected.append(edge_id)
            positions[v] = len(vertices)
            vertices.append(v)
    if vertices[-1] != target:
        raise RuntimeError("original-edge reconstruction has wrong target")
    weights, path = [], []
    for edge_id in selected:
        budget.check("reconstruction")
        weights.append(graph.original_edges[edge_id][2])
    for node in vertices:
        budget.check("reconstruction")
        path.append(graph.nodes[node])
    cost = math.fsum(weights)
    if not math.isclose(cost, distance, rel_tol=1e-10, abs_tol=1e-24):
        raise RuntimeError(f"reconstruction cost {cost} != index distance {distance}")
    return path, selected, cost


class BaseIndex:
    def assert_compatible(self, edges, nodes):
        value = graph_hash(edges, nodes)
        if value != self.graph_hash:
            raise GraphMismatch("graph topology/weights differ: rebuild this index")
        return value

    def _start_query(self, source, target, seconds, expected_hash):
        started = time.perf_counter()
        budget = QueryBudget(seconds, started)
        budget.check(force=True)
        if expected_hash is not None and expected_hash != self.graph_hash:
            raise GraphMismatch("query expected_graph_hash differs from index graph_hash")
        s, t = self.graph.node_index[source], self.graph.node_index[target]
        return s, t, started, budget

    def _finish_build(self, budget):
        self.graph_hash = self.graph.graph_hash
        self.stats.update(node_count=len(self.graph.nodes),
                          input_arc_count=len(self.graph.original_edges),
                          effective_arc_count=self.graph.edge_count,
                          graph_hash=self.graph_hash, status="OK",
                          preprocessing_s=0.0, index_memory_bytes=0,
                          footprint_accounting="deduplicated_sys_getsizeof_object_snapshot")
        self.stats["index_memory_bytes"] = deep_size(self, budget)
        if self.stats["index_memory_bytes"] > budget.cap:
            raise BudgetExceeded("RESOURCE_LIMIT", "preprocessing",
                                 "retained index footprint exceeds memory cap", self.stats)
        budget.check(force=True)
        self.stats["preprocessing_s"] = time.perf_counter() - budget.started

    def _result(self, source, target, distance, edge_ids, started, distance_s,
                reconstruction_started, budget, search_stats):
        path, edge_ids, cost = finish_original_path(
            self.graph, source, target, edge_ids, distance, budget)
        budget.check("reconstruction", force=True)
        reconstruction_s = time.perf_counter() - reconstruction_started
        return {
            "status": "UNREACHABLE" if math.isinf(distance) else "OK",
            "distance": distance, "path": path, "edge_ids": edge_ids, "path_cost": cost,
            "distance_query_s": distance_s, "reconstruction_s": reconstruction_s,
            "query_total_s": time.perf_counter() - started,
            "graph_hash": self.graph_hash, "search_stats": search_stats,
        }


def validate_order(graph, order, default):
    if order is None:
        return default
    order = list(order)
    try:
        indices = [graph.node_index[node] for node in order]
    except KeyError as exc:
        raise ValueError("order must be a permutation of all nodes") from exc
    if len(indices) != len(graph.nodes) or len(set(indices)) != len(indices):
        raise ValueError("order must be a permutation of all nodes")
    return indices
