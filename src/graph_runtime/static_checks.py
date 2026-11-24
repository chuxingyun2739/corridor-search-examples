"""Independent Dijkstra checks for the byte-preserved static CH/HL engines."""
import math
import networkx as nx
from static_engines import CHIndex, HubLabelIndex


def nominal_loss_graph(data):
    """Fixed nominal-voltage loss weights, not the state-dependent DVR objective."""
    cfg = data["config"]
    factor = (cfg["p_transfer_pu"] ** 2 + cfg["q_transfer_pu"] ** 2) / cfg["nominal_voltage_pu"] ** 2
    return [(branch["source"], branch["target"], branch["r_pu"] * factor)
            for branch in data["branches"]], list(data["nodes"])


def check_engine(engine, edges, nodes, *, preprocessing_timeout_s=10.0, memory_cap_mb=128.0,
                 query_timeout_s=2.0, order=None):
    index = engine.build(edges, nodes, preprocessing_timeout_s=preprocessing_timeout_s,
                         memory_cap_mb=memory_cap_mb, order=order)
    graph = nx.DiGraph()
    graph.add_nodes_from(nodes)
    for u, v, weight in edges:
        if not graph.has_edge(u, v) or weight < graph[u][v]["weight"]:
            graph.add_edge(u, v, weight=weight)
    records, errors = [], []
    for source in nodes:
        expected = nx.single_source_dijkstra_path_length(graph, source, weight="weight")
        for target in nodes:
            oracle = expected.get(target, math.inf)
            answer = index.query(source, target, query_timeout_s=query_timeout_s,
                                 expected_graph_hash=index.graph_hash)
            reachable = math.isfinite(oracle)
            distance_match = (math.isclose(answer["distance"], oracle, rel_tol=1e-10, abs_tol=1e-12)
                              if reachable else math.isinf(answer["distance"]))
            path = answer["path"]
            contiguous = len(answer["edge_ids"]) == max(0, len(path) - 1)
            for position, identifier in enumerate(answer["edge_ids"]):
                u, v, _ = edges[identifier]
                contiguous = contiguous and (u, v) == (path[position], path[position + 1])
            reconstruction = (bool(path) and path[0] == source and path[-1] == target
                              and len(path) == len(set(path)) and contiguous
                              and math.isclose(answer["path_cost"], oracle, rel_tol=1e-10, abs_tol=1e-12)
                              if reachable else not path and not answer["edge_ids"])
            two_hop = None
            if isinstance(index, HubLabelIndex):
                label_distance = index.label_distance(source, target)
                two_hop = (math.isclose(label_distance, oracle, rel_tol=1e-10, abs_tol=1e-12)
                           if reachable else math.isinf(label_distance))
            passed = distance_match and reconstruction and two_hop is not False
            if not passed:
                errors.append({"source": source, "target": target,
                               "distance_match": distance_match, "reconstruction": reconstruction,
                               "two_hop": two_hop})
            # JSON has no Infinity value: unreachable distance is explicitly null.
            safe_answer = {key: None if isinstance(value, float) and not math.isfinite(value) else value
                           for key, value in answer.items()}
            records.append({"source": source, "target": target,
                            "oracle_distance": oracle if reachable else None,
                            "reachable": reachable, "dijkstra_checked": True,
                            "distance_match": distance_match, "path_reconstruction_valid": reconstruction,
                            "two_hop_distance_matches": two_hop, "passed": passed, "answer": safe_answer})
    return {"engine": engine.__name__, "graph_hash": index.graph_hash,
            "build": dict(index.stats), "query_count": len(records), "queries": records,
            "issues": errors, "validation_status": "PASS" if not errors else "FAIL"}


ENGINES = (CHIndex, HubLabelIndex)
