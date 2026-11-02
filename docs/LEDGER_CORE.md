# Ledger Core

Mellow v2.8.0 provides an immutable, deterministic double-entry ledger for
business-rule scripts and audit-friendly prototypes.

## Transaction Model

Each posting has an account and a signed Decimal amount:

```mellow
[
    {"account": "cash", "amount": "100.00"},
    {"account": "revenue", "amount": "-100.00"}
]
```

The amounts must sum to `0.00`. A transaction ID may appear only once.

## Immutability

`ledger_post` returns a new ledger. It does not modify the input ledger. Use the
returned value for subsequent transactions.

## Verification

Entries contain `previous_hash` and `hash` fields. Hashes use canonical JSON and
SHA-256. `ledger_verify` checks:

- unique transaction IDs
- balanced postings
- currency consistency
- the complete hash chain
- the ledger head hash

No timestamp is inserted automatically, so identical inputs produce identical
hashes. A caller may include an explicit timestamp in the metadata map.

## Native Runtime

Since v2.9.7 the five ledger built-ins (`ledger_create`, `ledger_post`,
`ledger_verify`, `ledger_balance`, `ledger_entries`, also reachable as
`ledger.*` after `use ledger as ledger`) are implemented in C inside the
standalone runtime in `native/standalone/src/mellowrt_ledger.c`. Amounts use
cents-based 64-bit integers, and the canonical JSON pre-image is byte-identical
to the Python reference, so a hash produced by `mellow` verifies a ledger built
by `mellowlang.ledger_core` and the other way round.
`tests/native/test_full_native_c_cli.py` pins that parity, including the
`ledger: …` error messages.

## Security Boundary

Ledger Core does not provide durable persistence, user authentication,
authorization, digital signatures, payment processing, or regulatory
compliance. A production host must store ledgers transactionally, restrict who
can post, sign or externally anchor audit records, and maintain backups.
