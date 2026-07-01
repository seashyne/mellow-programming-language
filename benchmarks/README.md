# Mellow Benchmarks

Use `benchmarks/run_all.py` as the standard entry point for performance runs.
It orchestrates the existing focused benchmarks, records environment metadata,
writes a machine-readable JSON payload, and generates a Markdown summary.

## Profiles

| Profile | Use | Notes |
| --- | --- | --- |
| `quick` | Local smoke checks | Short repeat counts, suitable before/after a small change. |
| `ci` | Release gates and pull requests | Stable enough for regression tracking without taking too long. |
| `full` | Manual performance reports | Higher repeat counts and larger data workloads. |

## Commands

```powershell
python benchmarks\run_all.py --profile quick
python benchmarks\run_all.py --profile ci
python benchmarks\run_all.py --profile full
```

By default, reports are written under `benchmarks/reports/standard/` as paired
`.json` and `.md` files.

To compare against an earlier standard-suite JSON:

```powershell
python benchmarks\run_all.py --profile ci --baseline benchmarks\reports\standard\previous-ci.json
```

To skip cross-language timings when optional tools are missing:

```powershell
python benchmarks\run_all.py --profile quick --skip-cross-language
```

## Included Sections

- Standalone native runtime startup plus execution.
- Python package runtime, compile cache, and CLI startup.
- Data stream core throughput.
- Native data transform throughput.
- Cross-language microbenchmarks against Zig, C, Python, and Lua when available.
