# Reproducibility scope

Version v1.0.0 accompanies manuscript Access-2026-57387. The following levels define which inputs, operations and claims a reader can check locally.

| Level | Supplied inputs | Operation and interpretation |
|---|---|---|
| L1 | Historical four-node authored fixture | Three real searches and one fresh enumeration give a smoke check. |
| L2 | Nine fixed graph cases | HA-Reference, Adaptive and independent Exact-LC perform 27 searches and nine fresh enumerations. A separate check runs 232 ordered fixed-weight CH/HL queries across three graphs. |
| L3 | Five fixed graph cases, including a 13-node adverse example | Caps 3, 5, 10, 20 and 40 and three comparators make 40 calls. The adverse Adaptive gap is 1.085421%. The cap-3 and cap-5 outputs also retain suboptimal witnesses. |
| L4 | 249 frozen comparison rows | Recompute 11 summaries and compare 407 cells, preserving seven limited records. The original search outcomes, certificate claims and timings remain historical. |
| L5 | Five saved AC records, four selected certificate/control pairs and projected context | Verify 20 file identities and recalculate or compare 306 stored-data conditions. The recorded model hash and saved convergence flags are checked for consistency. |
| L6 | Complete native/corrected models, original AC runtime and complete replay inputs are absent | **Unsupported.** Fresh AC optimization, PF replay and the 504-method campaign cannot be reproduced from this subset. |

The 227 authored small graph inputs have independent frozen oracle references. The four-node smoke fixture and the separate 13-node adverse example lie outside the 227-case denominator. The smoke, correctness and caps commands make 70 method calls and ten enumeration checks in total. The adverse case appears in both the correctness and caps modes. Unit-test fixtures and static queries are counted separately.

The formal graph benchmark recorded 365 new calls and 86 reused records. The primary comparison contains 240 small/medium records and nine large records. Four medium IEEE inputs and three large-network model inputs are absent. The corresponding result rows support arithmetic reaggregation only.

Static CH/HL operates on fixed weights. Voltage-aware search maintains state across a path. L5 uses arrays and certificate statements saved during earlier AC executions. It does not recompute network equations or establish a new physical certificate. One limited method has an accepted incumbent and another has none. A blank metric means missing. These five illustrative records do not support an estimate of campaign-wide success.

The release records bounded local checks. Independent external reproduction has not been established.
