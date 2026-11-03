#!/usr/bin/env python3
"""Validate every example envelope against the schema.

This repo has no implementation, so the schema is the only machine-readable artefact in it.
An untested schema is decoration — this gives it the same treatment the rig's contract schema
gets, with the same exit-code discipline:

    0  all examples valid
    1  at least one example invalid
    3  could not look (schema unreadable, no examples, dependency missing)

"Nothing to validate" and "everything validated" must never share an exit code.
"""
from __future__ import annotations

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCHEMA_PATH = os.environ.get("NEO_SCHEMA_PATH") or os.path.join(
    ROOT, "schema", "envelope.v1.json")
EXAMPLE_GLOB = os.environ.get("NEO_EXAMPLE_GLOB") or os.path.join(
    ROOT, "examples", "*.json")


def die(why: str) -> None:
    print(f"COULD NOT LOOK: {why}", file=sys.stderr)
    raise SystemExit(3)


def main() -> int:
    try:
        import jsonschema
    except ImportError as exc:
        die(f"missing dependency: {exc}")

    try:
        with open(SCHEMA_PATH) as fh:
            schema = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        die(f"schema unreadable at {SCHEMA_PATH}: {exc}")

    paths = sorted(glob.glob(EXAMPLE_GLOB))
    if not paths:
        die(f"no examples matched {EXAMPLE_GLOB} — refusing to report success")

    validator = jsonschema.Draft202012Validator(schema)
    failures = 0
    for path in paths:
        name = os.path.basename(path)
        try:
            with open(path) as fh:
                doc = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"FAIL {name}: unreadable — {exc}")
            failures += 1
            continue
        errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
        if errors:
            failures += 1
            print(f"FAIL {name}: {len(errors)} schema violation(s)")
            for err in errors[:10]:
                where = "/".join(str(p) for p in err.path) or "<root>"
                print(f"  - {where}: {err.message}")
        else:
            print(f"ok   {name}")

    print(f"\n{len(paths)} example(s) read, {failures} invalid")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
