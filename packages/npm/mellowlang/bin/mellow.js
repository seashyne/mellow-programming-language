#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const packageRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(packageRoot, "..", "..", "..");

function platformKey() {
  const platform = process.platform;
  const arch = process.arch;
  if (!["win32", "linux", "darwin"].includes(platform)) {
    return null;
  }
  if (!["x64", "arm64"].includes(arch)) {
    return null;
  }
  return `${platform}-${arch}`;
}

function exeName() {
  return process.platform === "win32" ? "mellow.exe" : "mellow";
}

function candidates() {
  const name = exeName();
  const key = platformKey();
  const list = [];

  if (process.env.MELLOW_NATIVE_EXE) {
    list.push(process.env.MELLOW_NATIVE_EXE);
  }
  if (key) {
    list.push(path.join(packageRoot, "vendor", key, name));
  }

  list.push(path.join(repoRoot, "bin", name));
  list.push(path.join(repoRoot, "build", "standalone-release", "Release", name));
  list.push(path.join(repoRoot, "build", "standalone-release", name));
  list.push(path.join(repoRoot, "build", "standalone-bench-release", "Release", name));
  list.push(path.join(repoRoot, "native", "standalone", "build", "Release", name));
  list.push(path.join(repoRoot, "native", "standalone", "build", name));

  return list;
}

function findNativeExecutable() {
  for (const candidate of candidates()) {
    if (candidate && fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return null;
}

function printMissingExecutableHelp() {
  const key = platformKey() || `${process.platform}-${process.arch}`;
  console.error("Mellow native executable was not found.");
  console.error("");
  console.error(`Platform: ${key}`);
  console.error("");
  console.error("Fix options:");
  console.error("  1. Run the native installer from a source checkout:");
  console.error("       Windows: .\\scripts\\install-native.ps1");
  console.error("       Linux/macOS: sh scripts/install-native.sh --add-path");
  console.error("  2. Set MELLOW_NATIVE_EXE to an existing native mellow executable.");
  console.error("  3. Reinstall this npm package after CMake and a C compiler are available.");
}

const exe = findNativeExecutable();
if (!exe) {
  printMissingExecutableHelp();
  process.exit(1);
}

const result = spawnSync(exe, process.argv.slice(2), {
  stdio: "inherit",
  windowsHide: false
});

if (result.error) {
  console.error(result.error.message);
  process.exit(1);
}

process.exit(result.status === null ? 1 : result.status);
