#!/usr/bin/env python3
"""Pull national carbon intensity for a window (API-shape JSON).

Default: February 2025 -> data/uk_national_2025-02.json
(the held-out month for conformal-band validation, exp004).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from carbon_scheduling.data.neso import fetch_national

DEFAULT_START, DEFAULT_END = "2025-02-01T00:00Z", "2025-03-01T00:00Z"
DEFAULT_OUT = "data/uk_national_2025-02.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--out", default=DEFAULT_OUT, help="output path (repo-relative)")
    args = parser.parse_args()

    records = fetch_national(args.start, args.end)
    actuals = sum(1 for r in records if r["actual"] is not None)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"data": records}, indent=1) + "\n")
    print(f"wrote {len(records)} slots ({actuals} with actuals) -> {out}")


if __name__ == "__main__":
    main()
