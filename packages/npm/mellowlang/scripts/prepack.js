"use strict";

const fs = require("fs");
const path = require("path");

const packageRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(packageRoot, "..", "..", "..");
const source = path.join(repoRoot, "native", "standalone");
const target = path.join(packageRoot, "native", "standalone");

function copyRecursive(src, dest) {
  const stat = fs.statSync(src);
  if (stat.isDirectory()) {
    const base = path.basename(src);
    if (base === "build" || base === ".native-build") {
      return;
    }
    fs.mkdirSync(dest, { recursive: true });
    for (const entry of fs.readdirSync(src)) {
      copyRecursive(path.join(src, entry), path.join(dest, entry));
    }
    return;
  }
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.copyFileSync(src, dest);
}

if (!fs.existsSync(path.join(source, "CMakeLists.txt"))) {
  console.warn("[mellowlang] native standalone source not found; npm package will rely on external binary lookup");
  process.exit(0);
}

fs.rmSync(path.join(packageRoot, "native"), { recursive: true, force: true });
copyRecursive(source, target);
console.log("[mellowlang] bundled native/standalone source for npm package");
