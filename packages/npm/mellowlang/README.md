# mellowlang npm package

This package installs the `mellow` command for MellowLang 2.9.7.

It is native-first: Node.js is only used as an installer/wrapper. The language
runtime is the standalone C executable.

## Install from npm

```bash
npm install -g mellowlang
mellow doctor
mellow run hello.mellow
```

## Install from a source checkout

From the Mellow repository root:

```bash
npm install -g ./packages/npm/mellowlang
mellow doctor
```

During local source installs, the package builds `native/standalone` with CMake
and copies the native executable into this package's `vendor/` directory.

## Environment variables

- `MELLOW_NATIVE_EXE=/path/to/mellow` — force the wrapper to use a specific
  native executable.
- `MELLOW_NPM_SKIP_INSTALL=1` — skip the postinstall build step.

## Requirements for source installs

- CMake 3.16+
- A C compiler supported by CMake

For end users, published packages should ship or download prebuilt native
binaries per platform.
