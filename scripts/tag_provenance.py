#!/usr/bin/env python3
"""tag_provenance.py — Assign source provenance tags to normalized trace corpora.

Deterministically assigns each trace a source_id and marks a fraction of
sources as compromised (for poisoning simulation experiments).

Usage:
    py scripts/tag_provenance.py --corpus dacapo-synth [--num-sources 10] [--compromised-fraction 0.2]
    py scripts/tag_provenance.py --all-corpora
"""

import argparse
import json
import math
import random
import sys
from pathlib import Path


# NOTE on native source attribution:
# None of our five corpora (texada-bundled, crv2014, dacapo-synth, fsm-generated,
# posix-syscall) carry per-trace source metadata in their raw or normalized form.
# If a future corpus provides a "source" field in its JSONL or CSV, this function
# should be updated to parse that field instead of using round-robin assignment.


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


def tag_corpus(corpus_name: str, norm_dir: Path, out_dir: Path,
               num_sources: int, compromised_fraction: float, seed: int) -> None:
    corpus_path = norm_dir / f"{corpus_name}.txt"
    if not corpus_path.exists():
        print(f"  [SKIP] {corpus_name}: normalized file not found at {corpus_path}")
        return

    traces = read_texada(corpus_path)
    n = len(traces)
    print(f"  Loaded {n} traces from {corpus_path.name}")

    rng = random.Random(seed)

    # Assign source_ids: round-robin base, then permute with seed
    base_assignment = [i % num_sources for i in range(n)]
    permuted_indices = list(range(n))
    rng.shuffle(permuted_indices)
    source_ids = [0] * n
    for pos, orig_idx in enumerate(permuted_indices):
        source_ids[orig_idx] = base_assignment[pos]

    # Mark compromised sources
    n_compromised = max(1, math.floor(num_sources * compromised_fraction))
    # Deterministically choose which source_ids are compromised
    all_source_ids = list(range(num_sources))
    rng.shuffle(all_source_ids)
    compromised_set = set(all_source_ids[:n_compromised])

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{corpus_name}_provenance.jsonl"

    per_source_counts: dict[int, int] = {i: 0 for i in range(num_sources)}

    with open(out_path, "w", encoding="utf-8") as f:
        for trace_id, (trace, src_id) in enumerate(zip(traces, source_ids)):
            per_source_counts[src_id] += 1
            record = {
                "trace_id": trace_id,
                "source_id": src_id,
                "events": trace,
                "compromised": src_id in compromised_set,
            }
            f.write(json.dumps(record) + "\n")

    # Print summary
    n_compromised_traces = sum(1 for sid in source_ids if sid in compromised_set)
    print(f"  Sources: {num_sources}, compromised sources: {n_compromised} ({sorted(compromised_set)})")
    print(f"  Compromised traces: {n_compromised_traces} / {n} ({100*n_compromised_traces/max(1,n):.1f}%)")
    print(f"  Per-source counts: { {k: v for k, v in sorted(per_source_counts.items())} }")
    print(f"  Wrote {n} records to {out_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Assign deterministic source provenance tags to trace corpora."
    )
    parser.add_argument("--corpus", default=None, help="Corpus name (e.g. dacapo-synth)")
    parser.add_argument("--all-corpora", action="store_true", help="Process all normalized corpora")
    parser.add_argument("--num-sources", type=int, default=10, help="Number of sources (default: 10)")
    parser.add_argument("--compromised-fraction", type=float, default=0.2,
                        help="Fraction of sources marked compromised (default: 0.2)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    parser.add_argument("--norm-dir", default="data/normalized", help="Normalized data directory")
    parser.add_argument("--output", default="data/provenance", help="Output directory (default: data/provenance)")
    args = parser.parse_args()

    norm_dir = Path(args.norm_dir)
    out_dir = Path(args.output)

    if args.all_corpora:
        corpora = [f.stem for f in sorted(norm_dir.glob("*.txt"))]
        if not corpora:
            print("No normalized corpora found in", norm_dir)
            sys.exit(1)
    elif args.corpus:
        corpora = [args.corpus]
    else:
        parser.error("Specify --corpus NAME or --all-corpora")

    for corpus in corpora:
        print(f"\n[{corpus}]")
        tag_corpus(corpus, norm_dir, out_dir,
                   args.num_sources, args.compromised_fraction, args.seed)

    print("\nDone.")


if __name__ == "__main__":
    main()
