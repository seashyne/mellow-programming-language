# MellowLang v1.2.3

## Fixes

### Named args no longer conflict with normal maps (critical)

In v1.2.2, named args were compiled as a trailing plain map/dict. This was ambiguous with scripts that pass a normal map as a real argument (very common for game/AI data), for example:

```mellow
let data = {"hp": 10, "name": "slime"}
save_data("profile", data)
```

Because the second argument is a map, the VM mistakenly treated it as kwargs and removed it, causing an error like:

`save_data expects 2 args`

**v1.2.3 fix:** named args are now compiled as a tagged object:

```mellow
{"$kwargs": {"mode": "w"}}
```

The VM only extracts kwargs when that `"$kwargs"` tag is present, so normal maps are safe.

## Tests

- Added a regression test ensuring `save_data("profile", { ... })` does not get mis-read as kwargs.
