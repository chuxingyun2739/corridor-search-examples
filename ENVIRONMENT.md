# Environment and dependency identity

The supported validation environment is Windows x64 with CPython 3.13.3 in a fresh virtual environment, NetworkX 3.5 and psutil 7.1.2. `scripts/check_environment.py` checks Python version, operating system, bitness, both package versions and virtual-environment isolation. Other platforms have not been validated. Install CPython separately.

| Dependency | Official wheel | SHA-256 |
|---|---|---|
| NetworkX 3.5 | `networkx-3.5-py3-none-any.whl` | `0030d386a9a06dee3565298b4a734b68589749a544acbb6c412dc9e2489ec6ec` |
| psutil 7.1.2 | `psutil-7.1.2-cp37-abi3-win_amd64.whl` | `8e17852114c4e7996fe9da4745c2bdef001ebbf2f260dec406290e66628bdb91` |

The psutil wheel uses the Windows x64 stable ABI. [requirements.txt](requirements.txt) lists exactly these versions and wheel hashes. By default the second [README command](README.md) obtains the files from the official PyPI index. Once installed, the checks read the supplied files locally. The dependency notices are in [notices](notices).

## Offline setup with verified wheels

If you already have both official wheels, place them in a folder named `wheelhouse` beside the extracted repository. After the first README command creates the virtual environment, save the following as `.venv/pip.ini`. Then run the remaining README commands from the same repository root.

```ini
[global]
no-index = true
find-links = ../wheelhouse
```

This pip configuration selects only the supplied wheel directory for that virtual environment. The README installation command still checks each wheel against `requirements.txt`. The local release validation uses this option. The historical same-host candidate validation used the official index directly.

The earlier four-node smoke runner used psutil 7.0.0. This version calls the archived fixture and core through the R3 wrapper with psutil 7.1.2. No AC package or solver is required for the saved-record checks. A bounded validation runtime measures only this host and these commands.
