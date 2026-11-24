"""Shared evidence evaluation and explicitly named baseline adapters.

Archived Round5 source is imported unchanged. This module adds validation and
measurement, not a replacement search algorithm.
"""
from pathlib import Path
from dataclasses import asdict, replace
import itertools
import math
import sys
import time

SCRIPTS = Path(__file__).resolve().parent
BASE = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS / "vendor_round5"))
from src.round5.models import BranchPU, GraphPU, SupportSpec
from src.round5.vamls import VAMLSConfig, run_vamls
from src.round5.baselines import state_augmented_dijkstra, no_dominance_elementary_label_search

METHODS = ["optimized_dijkstra_post_eval", "bidirectional_dijkstra_post_eval",
           "astar_hop_lower_bound_post_eval", "alt_4_landmarks_post_eval",
           "yen_k8_paths_post_eval", "state_augmented_dijkstra_round5",
           "no_dominance_elementary_round5", "round5_reference", "label_capped_3_round5"]


class ResourceLimit(RuntimeError):
    pass


class BudgetGraph:
    def __init__(self, graph, deadline, expansion_limit=20000):
        self.adjacency = graph.adjacency
        self._nodes = graph.nodes
        self.deadline = deadline
        self.expansion_limit = expansion_limit
        self.calls = 0

    @property
    def nodes(self):
        return self._nodes

    def neighbors(self, node):
        self.calls += 1
        if time.perf_counter() > self.deadline:
            raise TimeoutError("algorithm deadline exceeded")
        if self.calls > self.expansion_limit:
            raise ResourceLimit("20000 adjacency expansions exceeded; not an infeasibility certificate")
        return self.adjacency.get(node, [])


def load_case_dict(data):
    adj = {int(n): [] for n in data["nodes"]}
    for br in data["branches"]:
        branch = BranchPU(**br)
        adj[branch.source].append(branch)
    graph = GraphPU(adj)
    specs = {int(n): SupportSpec(**v) for n,v in data["supports"].items()}
    cfg = VAMLSConfig(**data["config"])
    return graph, data["source"], data["target"], specs, cfg


def common_evaluate(graph, path, chosen_supports, specs, cfg, source, target):
    """Independent fixed-transfer recurrence with full output-policy checks."""
    path, chosen = tuple(path), tuple(chosen_supports)
    failure = {"feasible": False, "objective": None, "active_loss": None, "reactive_loss": None,
               "voltage_drop": None, "terminal_voltage": None, "minimum_voltage": None,
               "pre": [], "operational": [], "support_events": [], "reasons": []}
    reasons = []
    if not path or path[0] != source or path[-1] != target:
        reasons.append("missing path or wrong endpoints")
    if len(path) != len(set(path)):
        reasons.append("non-elementary path")
    if len(chosen) != len(set(chosen)):
        reasons.append("duplicate support declaration")
    if len(chosen) > cfg.max_support_nodes:
        reasons.append("support-count limit exceeded")
    if not set(chosen).issubset(path):
        reasons.append("support outside path")
    if source in chosen and not cfg.allow_support_at_source:
        reasons.append("source support forbidden")
    if target in chosen and not cfg.allow_support_at_target:
        reasons.append("target support forbidden")
    for n in chosen:
        sp = specs.get(n)
        if not sp or not sp.available or sp.capacity_pu <= 0:
            reasons.append(f"support unavailable at {n}")
    if any(not math.isfinite(v) for v in (cfg.nominal_voltage_pu,cfg.p_transfer_pu,cfg.q_transfer_pu)):
        reasons.append("non-finite configuration")
    if reasons:
        failure["reasons"] = reasons
        return failure
    lookup = {(b.source,b.target):b for bs in graph.adjacency.values() for b in bs}
    voltage = cfg.nominal_voltage_pu
    pre, op, events = [voltage], [voltage], []
    ploss = qloss = costs = gross_drop = 0.0

    def support(n, raw):
        nonlocal costs
        sp = specs[n]
        after = min(cfg.nominal_voltage_pu, raw + sp.capacity_pu)
        delta = max(0.0, after-raw)
        cost = cfg.lambda_support_count + sp.fixed_cost + (cfg.lambda_support_capacity+sp.unit_cost)*delta
        costs += cost
        events.append({"node":n,"before":raw,"after":after,"used_capacity":delta,"cost":cost})
        return after

    if source in chosen:
        voltage = support(source,voltage)
        op[0]=voltage
    for u,v in zip(path,path[1:]):
        b = lookup.get((u,v))
        if b is None:
            reasons.append(f"missing edge {u}->{v}")
            break
        if voltage <= 0 or not math.isfinite(voltage):
            reasons.append("nonpositive/nonfinite sending voltage")
            break
        current2 = (cfg.p_transfer_pu**2+cfg.q_transfer_pu**2)/voltage**2
        drop = (b.r_pu*cfg.p_transfer_pu+b.x_pu*cfg.q_transfer_pu)/voltage
        if b.r_pu < 0 or b.x_pu < 0:
            reasons.append("negative branch parameter outside supported model")
        if b.rate_pu is not None and math.hypot(cfg.p_transfer_pu,cfg.q_transfer_pu)>b.rate_pu+1e-12:
            reasons.append("branch apparent-power limit")
        ploss += b.r_pu*current2
        qloss += b.x_pu*current2
        gross_drop += drop
        raw = voltage-drop
        pre.append(raw)
        voltage = support(v,raw) if v in chosen else raw
        op.append(voltage)
    if any(not math.isfinite(v) or not cfg.voltage_lower_bound <= v <= cfg.voltage_upper_bound for v in op):
        reasons.append("operational voltage bound violation")
    return {"feasible":not reasons,"objective":ploss+costs,"active_loss":ploss,"reactive_loss":qloss,
            "voltage_drop":gross_drop,"terminal_voltage":voltage,"minimum_voltage":min(op),
            "pre":pre,"operational":op,"support_events":events,"reasons":reasons}


def nx_graph(graph, directed=False):
    import networkx as nx
    g = nx.DiGraph() if directed else nx.Graph()
    g.add_nodes_from(sorted(graph.nodes))
    for bs in graph.adjacency.values():
        for b in bs:
            g.add_edge(b.source,b.target,weight=math.hypot(b.r_pu,b.x_pu))
    return g


def static_path(g,source,target,method):
    import networkx as nx
    if method == METHODS[0]:
        return nx.dijkstra_path(g,source,target,weight="weight")
    if method == METHODS[1]:
        return nx.bidirectional_dijkstra(g,source,target,weight="weight")[1]
    if method == METHODS[2]:
        hops=nx.single_source_shortest_path_length(g.reverse(copy=False) if g.is_directed() else g,target)
        wmin=min(d["weight"] for _,_,d in g.edges(data=True))
        return nx.astar_path(g,source,target,heuristic=lambda u,t:hops.get(u,0)*wmin,weight="weight")
    if method == METHODS[3]:
        nodes=sorted(g.nodes)
        landmarks=nodes[::max(1,len(nodes)//4)][:4]
        forward={l:nx.single_source_dijkstra_path_length(g,l,weight="weight") for l in landmarks}
        if g.is_directed():
            reverse={l:nx.single_source_dijkstra_path_length(g.reverse(copy=False),l,weight="weight") for l in landmarks}
            def heuristic(u,t):
                values=[0.0]
                for l in landmarks:
                    if t in forward[l] and u in forward[l]:values.append(forward[l][t]-forward[l][u])
                    if u in reverse[l] and t in reverse[l]:values.append(reverse[l][u]-reverse[l][t])
                return max(values)
        else:
            def heuristic(u,t):
                return max([0.0]+[abs(d[t]-d[u]) for d in forward.values() if t in d and u in d])
        return nx.astar_path(g,source,target,heuristic=heuristic,weight="weight")
    raise ValueError(method)


def choose_supports(graph,paths,source,target,specs,cfg,deadline):
    best=None
    tested=0
    for path in paths:
        candidates=[n for n in path if n in specs and specs[n].available and specs[n].capacity_pu>0
                    and (n!=source or cfg.allow_support_at_source) and (n!=target or cfg.allow_support_at_target)]
        for k in range(min(cfg.max_support_nodes,len(candidates))+1):
            for chosen in itertools.combinations(candidates,k):
                if time.perf_counter()>deadline:
                    raise TimeoutError("post-evaluation deadline exceeded")
                tested+=1
                ev=common_evaluate(graph,path,chosen,specs,cfg,source,target)
                if ev["feasible"] and (best is None or ev["objective"]<best[2]["objective"]):
                    best=(tuple(path),chosen,ev)
    return best,tested


def run_method(data, method, timeout_seconds=5.0, profile=False):
    import networkx as nx
    graph,source,target,specs,cfg=load_case_dict(data)
    before=time.perf_counter()
    guarded=BudgetGraph(graph,before+timeout_seconds)
    metadata={"expanded_labels":None,"generated_labels":None,"dominated_labels":None,
              "constraint_pruned_labels":None,"heuristic_pruned_labels":None,
              "max_active_labels":None,"branches_evaluated":None,
              "support_action_labels_generated":None,"backtracking_count":0}
    if profile:
        import tracemalloc
        tracemalloc.start()
    error=""
    status="RUN"
    try:
        if method in METHODS[:5]:
            g=nx_graph(graph,data.get("directed",False))
            paths=itertools.islice(nx.shortest_simple_paths(g,source,target,weight="weight"),8) if method==METHODS[4] else [static_path(g,source,target,method)]
            best,tested=choose_supports(graph,paths,source,target,specs,cfg,guarded.deadline)
            path,supports,ev=best if best else ((),(),None)
            internal_feasible=best is not None
            internal_objective=ev["objective"] if ev else None
            metadata["support_configurations_evaluated"]=tested
        else:
            if method==METHODS[5]:
                result=state_augmented_dijkstra(guarded,source,target,specs,cfg)
            elif method==METHODS[6]:
                result=no_dominance_elementary_label_search(guarded,source,target,specs,cfg)
            elif method==METHODS[7]:
                result=run_vamls(guarded,source,target,specs,cfg)
            elif method.startswith("label_capped_"):
                cap=int(method.split("_")[2])
                result=run_vamls(guarded,source,target,specs,replace(cfg,heuristic_label_cap=cap))
            else:
                raise NotImplementedError(method)
            label=result.best_label
            path=label.path if label else ()
            supports=label.support_nodes if label else ()
            internal_feasible=result.feasible
            internal_objective=label.objective if label else None
            for key in metadata:
                if hasattr(result,key):metadata[key]=getattr(result,key)
        ev=common_evaluate(graph,path,supports,specs,cfg,source,target)
    except (TimeoutError,ResourceLimit,NotImplementedError,nx.NetworkXNoPath) as exc:
        status={TimeoutError:"TIMEOUT",ResourceLimit:"RESOURCE_LIMIT",NotImplementedError:"NOT_IMPLEMENTED",nx.NetworkXNoPath:"NO_PATH"}[type(exc)]
        error=str(exc)
        path=supports=()
        internal_feasible=False if status=="NO_PATH" else None
        internal_objective=None
        ev=common_evaluate(graph,(),(),specs,cfg,source,target)
    except Exception as exc:
        status="ERROR"
        error=f"{type(exc).__name__}: {exc}"
        path=supports=()
        internal_feasible=None
        internal_objective=None
        ev=common_evaluate(graph,(),(),specs,cfg,source,target)
    runtime_ms=(time.perf_counter()-before)*1000
    peak=None
    if profile:
        _,peak=tracemalloc.get_traced_memory()
        peak/=1024**2
        tracemalloc.stop()
    if status in ("TIMEOUT","RESOURCE_LIMIT","ERROR","NOT_IMPLEMENTED"):
        ev["feasible"]=None
    return {"case":data["case"],"method":method,"status":status,"runtime_ms":runtime_ms,
            "feasible_internal":internal_feasible,"objective_internal":internal_objective,
            "common":ev,"path":path,"support_nodes":supports,"stats":metadata,
            "error_message":error,"memory_peak_mb":peak,
            "evaluation_disagreement": bool(internal_feasible is True and (ev["feasible"] is not True or not math.isclose(internal_objective,ev["objective"],rel_tol=1e-7,abs_tol=1e-9)))}
