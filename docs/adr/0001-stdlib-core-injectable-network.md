# 0001 - Standard-library core, network only through injectable `fetch`

- Status: accepted
- Date: 2026-11-13

## Context
aidemy_pub runs this inside scheduled jobs; tests must run offline and fast, and the
sandbox/CI often has no network. Real API responses still have to be exercised.

## Options
1. Use `requests`/google-api-python-client directly everywhere.
2. Pure stdlib core; every network call goes through a `fetch(url, params)` callable.

## Decision
Option 2. `requests` is an optional extra (`[http]`). Unit tests inject recorded responses
in the real API shape; live checks are opt-in (`pytest -m live`).

## Consequences
+ Deterministic, offline, fast tests; easy to record real responses as fixtures.
- Live behaviour can drift (API shape changes) - covered by the `live` test marker.
