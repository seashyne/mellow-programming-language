# Mellow 1.5.3 Public Registry Flow

## Set the official registry
```bash
mellow pkg registry https://registry.mellowlang.org
```

## Save a publish token
```bash
mellow login --token your-secret-token
```

## Publish a package
```bash
mellow publish ./dialoguekit
```

## Search and install
```bash
mellow search dialogue
mellow install dialoguekit
```
