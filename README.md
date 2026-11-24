# Corridor search examples

Companion materials for **Voltage-Aware Multi-Label Search with Bounded Support Actions for Fast Power-Network Corridor Screening**, manuscript **Access-2026-57387**. Version **v1.0.0** contains graph-search code, authored graph fixtures, frozen result tables and selected saved AC evidence. The public subset supports the following checks on a local machine.

| Level | What the commands check | Expected result |
|---|---|---|
| L1 | Four-node graph smoke test | Three method calls and one fresh enumeration, with objective 0.02020304050607081 |
| L2 | HA-Reference, Adaptive and Exact-LC on nine fixed graph cases | 27 method calls and nine fresh enumerations |
| L3 | Fixed caps 3, 5, 10, 20 and 40, plus three comparators on five fixed cases | 40 method calls, including the 13-node adverse case |
| L4 | Reaggregation of 249 frozen graph-search records | 11 summary rows, 407 matching cells and seven retained limited records |
| L5 | Identities and arithmetic in five saved AC method records with four selected certificates | 20 file hashes and 306 consistency checks |
| L6 | Fresh AC optimization, power flow and full campaign replay | Unsupported. Complete native/corrected models, the original solver environment and full replay inputs are absent. |

The supplementary static CH/HL check compares 232 ordered path/distance queries against Dijkstra on three small graphs. These queries use fixed edge weights. The voltage-aware searches track the path and prior support actions. The local validation provides no independent external reproduction.

## Run the checks

Start in the directory containing this README, on Windows x64 with CPython 3.13.3 available as `python`. In PowerShell, run the following commands in order. The installation checks the wheel hashes in `requirements.txt`. An offline option using the same official wheels is described in [ENVIRONMENT.md](ENVIRONMENT.md).

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip --isolated --disable-pip-version-check install --no-cache-dir --index-url https://pypi.org/simple --require-hashes -r requirements.txt
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe -X utf8 -B scripts/check_environment.py
.venv\Scripts\python.exe -X utf8 -B scripts/verify_integrity.py
.venv\Scripts\python.exe -X utf8 -B scripts/run_graph.py smoke --output outputs/smoke.json
.venv\Scripts\python.exe -X utf8 -B scripts/run_graph.py correctness --output outputs/correctness.json
.venv\Scripts\python.exe -X utf8 -B scripts/run_graph.py caps --output outputs/caps.json
.venv\Scripts\python.exe -X utf8 -B scripts/run_ch_hl.py --output outputs/ch_hl.json
.venv\Scripts\python.exe -X utf8 -B scripts/reaggregate.py
.venv\Scripts\python.exe -X utf8 -B scripts/verify_ac_saved.py
.venv\Scripts\python.exe -X utf8 -B -m unittest discover -s tests -p "test_*.py" -v
```

The first two commands set up an isolated environment with NetworkX 3.5 and psutil 7.1.2. The next ten check dependencies, runtime, file integrity, graph behavior, frozen tables, saved AC records and 37 unit tests. Scripts write new output under `outputs/` or to the terminal. Keep the supplied files under `results/frozen/` for comparison. See the [validation protocol](docs/VALIDATION_PROTOCOL.md) for the expected result of each command.

## Interpret the results

The 13-node example gives Adaptive objective `0.012266122446467888` and exact/enumerated objective `0.012134412970375784`. Adaptive is about **1.085421%** above the optimum. The caps output retains the suboptimal cap-3 and cap-5 witnesses in `negative_outcomes`. A passing check reproduces these misses.

The repository includes 227 authored small inputs with frozen oracle references. The four-node smoke fixture and the separate adverse example lie outside that denominator. The three graph commands together make 70 method calls and ten enumerations on bounded cases. The full formal 249-row graph comparison and historical runtimes remain frozen. Medium IEEE and large-network rows whose input models are absent support L4 arithmetic only. Unknown global optimality gaps remain `NA`.

The saved AC sample includes two `RESOURCE_LIMIT` results. The IEEE57 L110 example has an accepted incumbent. The IEEE57 L115 example has none, and its physical metrics remain missing. L5 recomputes selected arithmetic from stored arrays and checks recorded flags. The five illustrative records do not establish campaign-wide success rates. The full 504-method AC campaign and fresh PF solving are outside this release's scope. Details are in [the saved AC guide](benchmarks/ac_saved/README.md).

## Find the implementation and verify the files

| Material | Location |
|---|---|
| Original history-aware and Adaptive search | [joint_search.py](src/graph_runtime/scripts/joint_search.py) |
| Independent FIFO Exact-LC adaptation and its assumptions | [exact_label_correcting.py](src/graph_runtime/exact_label_correcting.py) and [adaptation notes](configs/graph/EXACT_LC_ADAPTATION.md) |
| Fixed-cap adapter and static CH/HL implementations | [fixed_cap.py](src/graph_runtime/fixed_cap.py) and [static_engines](src/static_engines) |
| Authored graph inputs and independent saved oracles | [graph fixtures](benchmarks/graph) |
| Primary graph records, limited results and expected summaries | [frozen tables](results/frozen) |

The graph model uses a path-based voltage surrogate and fixed transfers. Meshed-network nodal balance and cycle consistency require a different physical model. Exact-LC is an independent, model-specific adaptation. Adaptive shares a query deadline across attempts. A per-attempt label limit therefore does not equalize cumulative work across methods. Frozen timings describe the original sessions.

[SOURCE_PROVENANCE.csv](SOURCE_PROVENANCE.csv) records source-member identities, transformations and release hashes for 305 files. [RELEASE_MANIFEST.csv](RELEASE_MANIFEST.csv) covers those files and the provenance table. [SHA256SUMS.txt](SHA256SUMS.txt) covers all 307 other files, including the release manifest. The full versioned tree or a separately hashed distribution archive also identifies the checksum file itself. Compare compressed bytes only against the digest of the same archive.

The author authorized public distribution of the selected research files and chose to add no new source or data license. NetworkX and psutil retain their own notices. See [third-party notices](THIRD_PARTY_NOTICES.md), the [six-level scope](REPRODUCIBILITY_SCOPE.md) and [v1.0.0 release notes](docs/release_notes.md).
