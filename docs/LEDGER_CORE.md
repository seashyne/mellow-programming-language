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

## Security Boundary

Ledger Core does not provide durable persistence, user authentication,
authorization, digital signatures, payment processing, or regulatory
compliance. A production host must store ledgers transactionally, restrict who
can post, sign or externally anchor audit records, and maintain backups.
