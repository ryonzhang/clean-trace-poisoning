#!/usr/bin/env python3
"""extract_legal_poison_pool.py — Extract antecedent-only traces as poison pool candidates.

Only SELECTS existing traces — never synthesizes or modifies traces.

Usage:
    py scripts/extract_legal_poison_pool.py --corpus dacapo-synth \
        --property "G(a->Fb)" --event-a fibonacci.enter --event-b fibonacci.exit
"""

import argparse
import json
import random
import sys
from pathlib import Path


def read_texada(path: Path) -> list[list[str]]:
    traces, current = [], []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == "":
            if current:
                traces.append(current)
                current = []
        else:
            current.append(stripped)
    if current:
        traces.append(current)
    return traces


def write_texada(path: Path, traces: list[list[str]]) -> None:
    lines = []
    for trace in traces:
        lines.extend(trace)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def is_antecedent_only(trace: list[str], event_a: str, event_b: str) -> bool:
    """Return True if event_a appears but event_b does NOT appear after the last event_a.

    A trace is an 'antecedent-only' counterexample to G(a -> F(b)) if:
    - event_a appears at least once
    - After the LAST occurrence of event_a, event_b does NOT appear
    """
    last_a_idx = None
    for i, e in enumerate(trace):
        if e == event_a:
            last_a_idx = i
    if last_a_idx is None:
        return False  # a never appears — no antecedent
    # Check if b appears after last a
    tail = trace[last_a_idx + 1:]
    return event_b not in tail


def main():
    parser = argparse.ArgumentParser(
        description="Extract antecedent-only traces as legal poison pool candidates."
    )
    parser.add_argument("--corpus", required=True, help="Corpus name (e.g. dacapo-synth)")
    parser.add_argument("--property", required=True, help='Property string (e.g. "G(a->Fb)")')
    parser.add_argument("--event-a", required=True, help="Antecedent event symbol")
    parser.add_argument("--event-b", required=True, help="Consequent event symbol")
    parser.add_argument("--split-seed", type=int, default=42, help="Seed for train/holdout split (default: 42)")
    parser.add_argument("--holdout-fraction", type=float, default=0.3, help="Fraction of traces in holdout (default: 0.3)")
    parser.add_argument("--norm-dir", default="data/normalized", help="Normalized data directory")
    parser.add_argument("--output-dir", default="data/poison_pool", help="Output directory")
    args = parser.parse_args()

    norm_dir = Path(args.norm_dir)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    corpus_path = norm_dir / f"{args.corpus}.txt"
    if not corpus_path.exists():
        print(f"ERROR: normalized corpus not found: {corpus_path}", file=sys.stderr)
        sys.exit(1)

    traces = read_texada(corpus_path)
    print(f"Loaded {len(traces)} traces from {corpus_path}")

    # Deterministic split
    rng = random.Random(args.split_seed)
    indices = list(range(len(traces)))
    rng.shuffle(indices)

    n_holdout = max(1, int(len(traces) * args.holdout_fraction))
    holdout_indices = indices[:n_holdout]
    model_indices = indices[n_holdout:]

    holdout_traces = [traces[i] for i in sorted(holdout_indices)]
    model_traces = [traces[i] for i in sorted(model_indices)]

    print(f"Split: {len(model_traces)} model traces, {len(holdout_traces)} holdout traces")

    # Extract antecedent-only traces from holdout
    pool_traces = [t for t in holdout_traces if is_antecedent_only(t, args.event_a, args.event_b)]
    print(f"Antecedent-only traces (poison pool candidates): {len(pool_traces)} / {len(holdout_traces)}")

    # Build output filename
    safe_a = args.event_a.replace(".", "_").replace("/", "_")
    safe_b = args.event_b.replace(".", "_").replace("/", "_")
    stem = f"{args.corpus}_{safe_a}_{safe_b}"

    pool_path = out_dir / f"{stem}_pool.txt"
    meta_path = out_dir / f"{stem}_pool_meta.json"

    write_texada(pool_path, pool_traces)
    print(f"Pool written to {pool_path}")

    meta = {
        "corpus": args.corpus,
        "property": args.property,
        "event_a": args.event_a,
        "event_b": args.event_b,
        "split_seed": args.split_seed,
        "holdout_fraction": args.holdout_fraction,
        "total_traces": len(traces),
        "total_holdout": len(holdout_traces),
        "total_model": len(model_traces),
        "antecedent_only_count": len(pool_traces),
        "fraction": round(len(pool_traces) / max(1, len(holdout_traces)), 6),
        "pool_path": str(pool_path),
        "note": "Only real traces selected; no synthesis or modification performed.",
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Metadata written to {meta_path}")

    if len(pool_traces) == 0:
        print("\nWARN: pool is empty. Try a different event-a/event-b pair or a corpus with more variation.")


if __name__ == "__main__":
    main()
