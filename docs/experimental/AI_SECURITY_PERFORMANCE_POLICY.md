# Mellow AI Security and Performance Policy

Mellow 2.9.x moves the product goal toward a small, fast, auditable runtime for AI-era applications.

## Release Gate

Every release candidate should pass:

- `mellow bench` for compiler, VM, and native host batching smoke benchmarks.
- `mellow security audit` for sandbox escape checks, AI tool policy checks, and package trust checks.
- `mellow release-gate` for the combined benchmark + sandbox + package integrity gate.

CI can also run:

```powershell
python scripts/package_release_gate.py
```

## Package Trust Model

Official packages must:

- declare `official = true`;
- declare one or more authors;
- keep `mellow.toml` and `mellow.pkg.json` in sync;
- build deterministic `.mpkg` archives without generated runtime state;
- verify archive paths so absolute paths and `..` traversal cannot enter archives;
- pass archive SHA-256 and signature verification during release gates.

Remote or third-party package installs should be treated as untrusted until the creator is explicitly trusted with `mellow trust <author>` or package verification succeeds under a strict policy.

## AI Tool Policy

AI tools are default-deny. An agent can call a tool only when at least one of these is true:

- the tool is passed explicitly to `mellow agent run --tool <name>`;
- the tool appears in `--allow-tool <name>`;
- a signed capability policy allows it.

Denied tools and denied capabilities always win over allow-lists.

## Native Host Batching

Hot host APIs should prefer coarse-grained native calls. `std.ai.llm_tensor_batch` is the reference shape: one host call can run multiple tensor operations, and the native extension can execute the batch without returning to Python between kernels.
