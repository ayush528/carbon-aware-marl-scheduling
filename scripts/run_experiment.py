#!/usr/bin/env python3
"""CLI wrapper: run a registered experiment and print its run record.

Usage: python scripts/run_experiment.py <exp-id>
The run record (manifest + metrics) is appended under
experiments/<exp-id>/runs/ -- commit it as evidence.
"""

from __future__ import annotations

import argparse
import json

from carbon_scheduling.runner import run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exp_id", help="experiment id, e.g. exp001-uk-carbon-baseline")
    args = parser.parse_args()
    record = run(args.exp_id)
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
