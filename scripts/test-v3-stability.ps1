$ErrorActionPreference = "Stop"

py -3.11 -m pytest -q tests/core tests/language -p no:cacheprovider

py -3.11 -m pytest -q `
  tests/test_v152_online_registry.py `
  tests/test_v153_public_registry.py `
  tests/test_v154_cli_registry.py `
  tests/test_v157_core_packages.py `
  tests/test_v158_lockfile.py `
  tests/test_v159_runtime_and_imports.py `
  tests/test_v215_package_runtime_integration.py `
  tests/test_v216_project_templates.py `
  -p no:cacheprovider
