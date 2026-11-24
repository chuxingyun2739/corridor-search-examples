# Selected saved AC evidence at L5

This directory contains five illustrative saved records for manuscript **Access-2026-57387**, version **v1.0.0**.

## What Can Be Reproduced

Use the canonical saved-AC verification and unittest discovery commands in the repository-root README. Run both with its pinned virtual-environment interpreter from the repository root.

The verifier checks the 20 input-file SHA256/size entries in `manifest.json` and
performs 306 arithmetic and identity assertions. It checks five historical method
records, four selected certificate/control pairs, 26 candidate-host mappings and
the five-row `selected_summary.csv`. Expected status: `PASS`, with zero failed
checks. The full 37-test suite includes 14 saved-AC tests, including deliberate corruption of
in-memory copies. The on-disk evidence is unchanged by either command.

The verifier covers the following items.

- Method, context, certificate, optimizer-status and summary identities.
- Consistency of saved convergence, acceptance, residual and termination flags.
- Candidate paths mapped to the original demand-ranked eligible AC hosts.
- Support Q bounds, totals and controls, and native Pg/Qg bounds and commands.
- Redispatch L1 calculated from saved Pg and reference Pg arrays.
- Vm minimum, maximum, maximum deviation and RMS calculated from saved Vm arrays.
- Saved branch-loading values compared with their saved limits.
- Saved active-generation/load/loss balance arithmetic and agreement between the
  saved B_LOSS objective, certificate loss and summary loss.
- Preservation of missing physical metrics in the uncertified limited record.

These are checks on saved arrays and historical certificate statements. They do
not newly establish that the electrical network satisfies its power-flow equations.
The stored model hash strings are checked for agreement; the native model whose
hash they record is not supplied and its hash is not recomputed.

## Expected Results

All records use the original `demand` host ranker and 20% redispatch cap.

| Scenario | Method | Method termination | Selected certificate | Saved loss (MW) |
|---|---|---|---|---:|
| IEEE30 L110 | DVR_MLS_PORTFOLIO_V2_ANCHOR | COMPLETED_FEASIBLE | Yes | 1.994822 |
| IEEE30 L110 | AC_K8 | COMPLETED_FEASIBLE | Yes | 2.035608 |
| IEEE57 L110 | DVR_MLS_PORTFOLIO_V2_ANCHOR | RESOURCE_LIMIT | Yes | 26.704252 |
| IEEE57 L110 | AC_K8 | COMPLETED_FEASIBLE | Yes | 25.327477 |
| IEEE57 L115 | DVR_MLS_PORTFOLIO_V2_ANCHOR | RESOURCE_LIMIT | No | NA |

The rows intentionally retain contrasting outcomes. A limited search may retain
an accepted incumbent; the method's terminal status and certificate flag answer
different questions. Missing physical results are not zero and do not prove
infeasibility. These five illustrative records are not a statistical sample from
which campaign-wide success rates or method superiority may be inferred.

For IEEE57 L110 V2, graph support actions occur at nodes 23 and 25, whereas the AC
hosts are 14, 38 and 47. The independently optimized support Q vector is about
(0, 13.333333, 0) Mvar. Graph voltage lifts are not Mvar controls. In the paired
records, V2 has lower loss on IEEE30 and higher loss on IEEE57. Lower loss does
not imply uniform improvement of voltage metrics.

The method files retain 84 historical stage-event records, of which 48 have an
accepted flag. Only the four selected certificate/status pairs are supplied and
checked. References to other stage certificates remain historical identifiers;
their files are not included or read by this verifier.

## Required Environment

The saved-evidence verifier uses the Python standard library. The validated interpreter is CPython 3.13.3. No NetworkX, CasADi, IPOPT,
pandapower, native model binary, solver license or network connection is required.
The repository's pinned environment is documented by the repository-level files.

The verifier and tests preserve the on-disk evidence and write their results to standard output or error.
`-B` prevents Python bytecode-cache files. The verifier rejects linked input paths,
absolute evidence references and parent-directory traversal.

## Provenance and Transformations

`manifest.json` records the source archive SHA256, original archive member names,
before/after file hashes, public file sizes, roles and transformations. It indexes
18 original source files plus the projected configuration and five-row summary.
The source is the authorized frozen private R3 reproduction archive; the archive
itself and its full 1,931-file AC supplement are not included here.

Thirteen source JSONs (five methods, four certificates and four optimizer-status
files) are preserved byte for byte. Five context copies retain exactly
`native_identity`, `model_hash`, `eligible`, `demand` and `reference`; their unused
`graph` payload is omitted. Every retained context value was compared with the
source before writing. Those five copies have different file hashes and are not
claimed to be byte-identical. No actual private path or private repository URL was
found in the selected public payloads. Relative scientific identifiers remain.

`selected_summary.csv` keeps the original source cell strings for the five listed
rows and its stated columns, including empty physical-result cells. `config.json`
projects the relevant frozen protocol fields and separately labels the new
checker's numerical tolerances. Host/path node IDs are one-based; generation bus
and certificate voltage-array IDs are zero-based, as in the original records.

## What Cannot Be Reproduced

**L6 is unsupported.** There are no complete native/corrected AC model inputs
or original AC execution environment. This module cannot rerun power flow, AC
optimization, the 504-method campaign, the complete historical fixed-control PF
replay, or every stage certificate. It does not reconstruct branch flows from
network admittance, freshly test nodal balance, prove global optimality, verify a
physical device calibration, or establish an independent-solver result.

## Interpretation and distribution

The convergence flags, nodal residuals and voltage-violation counts describe historical certificates. The verifier checks their consistency and recomputes selected support, generation and voltage metrics from the supplied arrays. The source-member hashes document the origin and identity of each file.

The author confirmed the rights to the selected IEEE30/IEEE57-derived values and authorized their public distribution with this release. See the repository's [third-party notices and author terms](../../THIRD_PARTY_NOTICES.md).
