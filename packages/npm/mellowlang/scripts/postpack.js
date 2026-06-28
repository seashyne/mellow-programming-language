"use strict";

const fs = require("fs");
const path = require("path");

const packageRoot = path.resolve(__dirname, "..");
fs.rmSync(path.join(packageRoot, "native"), { recursive: true, force: true });
console.log("[mellowlang] cleaned bundled native source after pack");
