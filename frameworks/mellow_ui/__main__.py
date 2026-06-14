from __future__ import annotations

import json

import frameworks.mellow_ui as UI


def DemoApp(props):
    return UI.Screen({
        "Name": props.get("name", "MellowUIDemo"),
        "Children": [
            UI.TextLabel("Hello Mellow UI", {"Size": [360, 60]}),
            UI.Button("Play", {"Size": [220, 54]}),
            UI.ProgressBar(0.5, {"Size": [220, 16]}),
        ],
    })


def build_demo_tree() -> dict:
    root = UI.createRoot("App")
    return root.render(UI.createElement(DemoApp, {"name": "MellowUIDemo"}))


def main() -> int:
    print(json.dumps(build_demo_tree(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
