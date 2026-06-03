# MellowLang 1.5.1 Overview

MellowLang 1.5.1 pushes the project closer to an AI-native language with five practical layers:

- **Package manager** for reusable modules and app shipping
- **Game scripting engine** helpers for scene/entity style projects
- **AI API** for one interface across offline providers
- **Compiler outputs** for bytecode inspection and Python generation
- **Documentation** that turns the runtime into a usable product

## Package manager

```bash
mellow pkg init hello_pkg --name hello-world
mellow pkg publish hello_pkg
mellow pkg install hello-world
mellow pkg build hello_pkg
```

## Game scripting engine

```mellow
keep game = get("game")
keep hero = call game["entity_create"]("hero", 2, 3, 1, 1)
keep box = call game["entity_create"]("box", 3, 3, 1, 1)
keep moved = call game["entity_move"](hero, 1, 0)
show call game["collide_aabb"](moved, box)
```

## AI API

```mellow
keep ai = get("ai")
show call ai["api_providers"]()
show call ai["api_complete"]("offline", "Summarize MellowLang in one line")
```

## Compiler

```bash
mellow compile examples/hello.mellow --target bytecode
mellow compile examples/hello.mellow --target python
```
