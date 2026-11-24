# Quick start

Open PowerShell in the directory containing [README.md](README.md). The twelve commands under **Run the checks** are the executable sequence for Windows x64 and CPython 3.13.3. For the exact wheel identities and the offline installation option, see [ENVIRONMENT.md](ENVIRONMENT.md).

1. Create a fresh virtual environment and install the two pinned dependency wheels.
2. Run the dependency, environment and integrity checks. The six pinned environment fields must pass, and 307 files must match `SHA256SUMS.txt`.
3. Run `smoke`, `correctness` and `caps`. Expect 3, 27 and 40 method calls, respectively. Inspect `negative_outcomes` in the latter two reports for the 13-node adverse case.
4. Run the static CH/HL checks (232 queries), frozen CSV reaggregation (249 rows and 407 cells), and saved AC verification (20 hashes and 306 conditions).
5. Run the test suite. The 37 tests cover source and input identities, graph witnesses, static paths and saved-evidence consistency. Some deliberately corrupt in-memory copies to check the verifier.

The environment and graph reports are written under `outputs/`. The table comparison writes under `outputs/reaggregation/`. The saved AC verifier and the unit tests print their results. A `RESOURCE_LIMIT` outcome and a missing physical measurement retain their original meaning in the frozen data. The bounded sequence ends at L5 and performs zero fresh AC/PF solves.
