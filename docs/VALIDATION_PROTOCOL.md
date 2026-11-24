# Bounded validation protocol

Run the twelve commands in the [root README](../README.md) once in order from a clean extraction. Two create the environment and install the dependencies. The other ten check the following outcomes.

| Command group | Expected condition |
|---|---|
| Dependency check | pip reports no broken requirements. |
| Environment | Windows, 64 bit, CPython 3.13.3, NetworkX 3.5, psutil 7.1.2 and virtual-environment isolation pass. |
| Integrity | All 307 entries in `SHA256SUMS.txt` match the supplied files. |
| L1 smoke | One input, three calls and one fresh enumeration, with objective approximately 0.02020304050607081. |
| L2 correctness | Nine inputs, 27 calls and nine fresh enumerations. Adaptive's registered adverse behavior is reproduced. |
| L3 caps | Five inputs, 40 calls, including the five caps and three comparison methods. Cap-3 and cap-5 adverse behavior is retained. |
| Static CH/HL | On three small inputs, all 232 ordered queries agree with Dijkstra on path validity and distance. |
| L4 frozen CSV | 249 primary rows, 11 summaries, 407 matching cells and seven retained limited records. |
| L5 saved AC | Five method records, four selected certificates, 20 file identities and 306 passing conditions. |
| Unit tests | 37 distinct tests pass, including deliberate corruption checks on in-memory copies. |

The three graph commands make 70 method calls and ten small enumeration checks. Unit-test fixtures and static queries are additional bounded work. Keep adverse outcomes and any failed or timed-out checks with their reports. L6 has no execution command. No fresh AC/PF solves are part of this procedure.

Elapsed times for these commands describe validation on the recorded host. The frozen research results retain their original timing and certificate fields. A same-host extraction and run does not establish independent external reproduction.
