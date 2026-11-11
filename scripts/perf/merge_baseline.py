"""Merge page/concurrency/idle/pytest results into before.json or after.json."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PERF_DIR = Path(__file__).resolve().parent
if str(PERF_DIR) not in sys.path:
    sys.path.insert(0, str(PERF_DIR))

from bench_common import RESULTS_DIR, load_json, write_json  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True, choices=["before", "after"])
    args = parser.parse_args()
    label = args.label

    def _opt(name: str):
        p = RESULTS_DIR / name
        if not p.is_file():
            return {"status": "NOT RUN", "blocker": f"missing {name}"}
        return load_json(p)

    payload = {
        "label": label,
        "pages": _opt(f"pages_{label}.json"),
        "concurrency": _opt(f"concurrency_{label}.json"),
        "idle": _opt(f"idle_{label}.json"),
        "pytest": _opt(f"pytest_{label}.json"),
        "investigation": None,
    }
    inv = RESULTS_DIR.parent / "investigation" / "concerns.json"
    if inv.is_file():
        payload["investigation"] = json.loads(inv.read_text(encoding="utf-8"))
    out = RESULTS_DIR / f"{label}.json"
    write_json(out, payload)
    # Official comparison alias used by the audit plan.
    alias = RESULTS_DIR / f"baseline_{label}.json"
    write_json(alias, payload)
    print(f"[perf] wrote {out}")
    print(f"[perf] wrote {alias}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
