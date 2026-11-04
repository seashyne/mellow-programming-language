"""The static files a generated React app is made of: package.json,
index.html, main.tsx, tsconfig.json and the Vite config."""

from __future__ import annotations

import json
from pathlib import Path


def _write_dev_file(path: Path, content: str) -> None:
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return
    path.write_text(content, encoding="utf-8")


def _dev_package_json() -> str:
    return json.dumps(
        {
            "private": True,
            "type": "module",
            "scripts": {
                "build": "vite build",
                "dev": "vite",
            },
            "dependencies": {
                "@vitejs/plugin-react": "^5.0.0",
                "vite": "^7.0.0",
                "typescript": "^5.8.0",
                "react": "^19.0.0",
                "react-dom": "^19.0.0",
            },
            "devDependencies": {},
        },
        indent=2,
    ) + "\n"


def _dev_index_html() -> str:
    return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Mellow Web</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
"""


def _dev_main_tsx() -> str:
    return """import React from "react"
import { createRoot } from "react-dom/client"
import MellowApp from "../MellowApp"

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <MellowApp />
  </React.StrictMode>,
)
"""


def _dev_tsconfig_json() -> str:
    return json.dumps(
        {
            "compilerOptions": {
                "jsx": "react-jsx",
                "module": "ESNext",
                "moduleResolution": "Bundler",
                "target": "ES2020",
                "strict": True,
                "skipLibCheck": True,
                "types": ["vite/client"],
            },
            "include": ["src", "MellowApp.tsx"],
        },
        indent=2,
    ) + "\n"


def _dev_vite_config() -> str:
    return """import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

export default defineConfig({
  plugins: [react()],
})
"""
