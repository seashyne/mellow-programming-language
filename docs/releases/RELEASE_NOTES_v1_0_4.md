# Release Notes — v1.0.4

- Improved `_print_pretty_error` to match Frinds-style output.
- `_cmd_run` now wraps compile+run to avoid raw Python tracebacks for syntax/runtime errors.
- `mellow check` now:
  1) compiles first (shows syntax errors with code frame),
  2) then prints lint issues with code frames.
