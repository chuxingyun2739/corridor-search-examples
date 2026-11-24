# Exact-LC adaptation boundary

`independent_exact_label_correcting` is an independently written FIFO elementary label-correcting adaptation motivated by Feillet et al. (2004), DOI 10.1002/net.20033. The original audit verified the publisher metadata and abstract but did not obtain the paper's full text. This repository therefore does not claim a complete reproduction of that paper or an author-released implementation.

The electrical transition and support policy are shared with the archived DVR-MLS implementation. With fixed nonnegative P/Q, nonnegative r/x and support prices, positive operational voltage, and support capped at nominal voltage, a higher sending voltage gives no lower arrival voltage, no higher branch loss, and no higher cost for the same support action. The implemented conservative dominance additionally requires compatible visited/support histories and no greater support count or accumulated cost components. The source docstring records this restricted continuation argument.

Only exhausted searches may certify an optimum or infeasibility. Limits and errors preserve any validated incumbent and otherwise mean unknown feasibility. No voltage discretization, per-node label cap, or voltage-based permanent-unreachability rule is introduced by Exact-LC.

General resource-extension, elementarity, label-correcting, and history-compatible dominance definitions were separately checked in Irnich and Desaulniers (2005), *Column Generation*, pp. 33-65, DOI 10.1007/0-387-25486-2_2, at printed pp. 37, 38, 49-51. Those page numbers do not refer to the 2004 paper. This repository does not redistribute either publication.

This release preserves the archived search functions and classes. The portable copy adjusts the repository-relative bootstrap and documentation pointer. Authorship and publication terms are described in [the third-party notices](../../THIRD_PARTY_NOTICES.md).
