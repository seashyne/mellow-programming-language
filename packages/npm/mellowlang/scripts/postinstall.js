"use strict";

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const packageRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(packageRoot, "..", "..", "..");

function log(message) {
  console.log(`[mellowlang] ${message}`);
}

function warn(message) {
  console.warn(`[mellowlang] ${message}`);
}

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

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    stdio: "inherit",
    windowsHide: false,
    ...options
  });
  return result.status === 0;
}

function existingNative() {
  if (process.env.MELLOW_NATIVE_EXE && fs.existsSync(process.env.MELLOW_NATIVE_EXE)) {
    return process.env.MELLOW_NATIVE_EXE;
  }
  const key = platformKey();
  if (!key) {
    return null;
  }
  const vendorExe = path.join(packageRoot, "vendor", key, exeName());
  return fs.existsSync(vendorExe) ? vendorExe : null;
}

function copyBuiltBinary(buildDir, vendorDir) {
  const name = exeName();
  const candidates = [
    path.join(buildDir, "Release", name),
    path.join(buildDir, name)
  ];
  const source = candidates.find((candidate) => fs.existsSync(candidate));
  if (!source) {
    return false;
  }
  fs.mkdirSync(vendorDir, { recursive: true });
  const target = path.join(vendorDir, name);
  fs.copyFileSync(source, target);
  if (process.platform !== "win32") {
    fs.chmodSync(target, 0o755);
  }
  return true;
}

function copyExistingCandidate(vendorDir) {
  const name = exeName();
  const candidates = [
    path.join(repoRoot, "bin", name),
    path.join(repoRoot, "build", "standalone-release", "Release", name),
    path.join(repoRoot, "build", "standalone-release", name),
    path.join(repoRoot, "build", "standalone-bench-release", "Release", name),
    path.join(repoRoot, "native", "standalone", "build", "Release", name),
    path.join(repoRoot, "native", "standalone", "build", name)
  ];
  const source = candidates.find((candidate) => fs.existsSync(candidate));
  if (!source) {
    return false;
  }
  fs.mkdirSync(vendorDir, { recursive: true });
  const target = path.join(vendorDir, name);
  fs.copyFileSync(source, target);
  if (process.platform !== "win32") {
    fs.chmodSync(target, 0o755);
  }
  log(`copied existing native executable from ${source}`);
  return true;
}

if (process.env.MELLOW_NPM_SKIP_INSTALL === "1") {
  log("postinstall skipped because MELLOW_NPM_SKIP_INSTALL=1");
  process.exit(0);
}

if (existingNative()) {
  log("native executable already available");
  process.exit(0);
}

const key = platformKey();
if (!key) {
  warn(`unsupported npm platform ${process.platform}-${process.arch}`);
  process.exit(0);
}

const bundledSourceRoot = path.join(packageRoot, "native", "standalone");
const repoSourceRoot = path.join(repoRoot, "native", "standalone");
const sourceRoot = fs.existsSync(path.join(bundledSourceRoot, "CMakeLists.txt"))
  ? bundledSourceRoot
  : repoSourceRoot;

if (!fs.existsSync(path.join(sourceRoot, "CMakeLists.txt"))) {
  warn("native source tree is not bundled in this npm package yet");
  warn("published packages should ship prebuilt vendor binaries or release download support");
  process.exit(0);
}

const vendorDir = path.join(packageRoot, "vendor", key);

if (copyExistingCandidate(vendorDir)) {
  process.exit(0);
}

log("building native C runtime from source");
const packageBuildDir = path.join(packageRoot, ".native-build", key);
if (!run("cmake", ["-S", sourceRoot, "-B", packageBuildDir, "-DCMAKE_BUILD_TYPE=Release"])) {
  warn("cmake configure failed; install CMake and a C compiler, then reinstall");
  process.exit(0);
}

const buildArgs = ["--build", packageBuildDir];
if (process.platform === "win32") {
  buildArgs.push("--config", "Release");
} else {
  buildArgs.push("--parallel");
}

if (!run("cmake", buildArgs)) {
  warn("native build failed; install a supported C compiler, then reinstall");
  process.exit(0);
}

if (copyBuiltBinary(packageBuildDir, vendorDir)) {
  log(`native executable installed to ${vendorDir}`);
} else {
  warn("native build completed but executable was not found");
}
