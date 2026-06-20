#!/usr/bin/env python3
"""gen_params_grid.py — Generate full Cartesian product parameter grid for experiments.

Outputs data/params_grid.csv.

Usage:
    py scripts/gen_params_grid.py [--output data/params_grid.csv]
"""

import argparse
import csv
import itertools
from pathlib import Path


PARAM_SPACE = {
    "poison_budget_K_pct":           [1, 2, 5, 10, 20],
    "target_antecedent_freq_bucket": ["low(<0.1)", "medium(0.1-0.3)", "high(>0.3)"],
    "confidence_threshold":          [0.8, 0.9, 0.95],
    "quorum_q":                      [2, 3, 5],
    "num_sources":                   [5, 10, 20],
    "compromised_source_fraction":   [0.1, 0.2, 0.3],
}


def main():
    parser = argparse.ArgumentParser(
        description="Generate full Cartesian product parameter grid for experiments."
    )
    parser.add_argument("--output", default="data/params_grid.csv",
                        help="Output CSV path (default: data/params_grid.csv)")
    args = parser.parse_args()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    keys = list(PARAM_SPACE.keys())
    values = list(PARAM_SPACE.values())
    combos = list(itertools.product(*values))

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for combo in combos:
            writer.writerow(dict(zip(keys, combo)))

    print(f"Parameter grid written to {out_path}")
    print(f"Total configurations: {len(combos)}")
    for k, v in PARAM_SPACE.items():
        print(f"  {k}: {v}")
    print(f"\nGrid dimensions: {' x '.join(str(len(v)) for v in values)} = {len(combos)}")


if __name__ == "__main__":
    main()
