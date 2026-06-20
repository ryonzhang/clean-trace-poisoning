#!/usr/bin/env python3
"""normalize.py — Normalize raw trace corpora to Texada format and build manifest.

Usage:
    py scripts/normalize.py [--input-dir data/raw] [--output-dir data/normalized] [--corpus NAME]
"""

import argparse
import json
import statistics
from pathlib import Path


CORPUS_META = {
    "texada-bundled": {"source": "https://github.com/ModelInference/texada", "license": "MIT"},
    "crv2014":        {"source": "https://www.react.uni-saarland.de/tools/crv2014/", "license": "see-SOURCES.md"},
    "dacapo-synth":   {"source": "generated", "license": "none"},
    "fsm-generated":  {"source": "generated", "license": "none"},
    "posix-syscall":  {"source": "generated", "license": "none"},
}


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


def collect_corpus_files(corpus_dir: Path) -> list[Path]:
    """Return all .txt files under corpus_dir."""
    return sorted(corpus_dir.glob("**/*.txt"))


def normalize_corpus(corpus_name: str, raw_dir: Path, out_dir: Path) -> dict:
    corpus_dir = raw_dir / corpus_name
    if not corpus_dir.exists():
        # Try flat file
        flat = raw_dir / f"{corpus_name}.txt"
        if flat.exists():
            files = [flat]
        else:
            raise FileNotFoundError(f"Corpus directory not found: {corpus_dir}")
    else:
        files = collect_corpus_files(corpus_dir)

    all_traces: list[list[str]] = []
    for f in files:
        traces = read_texada(f)
        all_traces.extend(traces)

    # Validate
    valid_traces = []
    skipped = 0
    for t in all_traces:
        if not t:
            skipped += 1
            continue
        # filter empty-string events
        events = [e for e in t if e.strip()]
        if events:
            valid_traces.append(events)
        else:
            skipped += 1

    if skipped:
        print(f"  [warn] {corpus_name}: skipped {skipped} empty traces")

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{corpus_name}.txt"
    write_texada(out_path, valid_traces)

    # Compute stats
    lengths = [len(t) for t in valid_traces]
    alphabet = sorted({e for t in valid_traces for e in t})
    num_events_total = sum(lengths)
    mean_len = statistics.mean(lengths) if lengths else 0.0

    meta = CORPUS_META.get(corpus_name, {"source": "unknown", "license": "unknown"})
    record = {
        "name": corpus_name,
        "source": meta["source"],
        "license": meta["license"],
        "num_traces": len(valid_traces),
        "num_events_total": num_events_total,
        "alphabet_size": len(alphabet),
        "alphabet": alphabet,
        "min_trace_len": min(lengths) if lengths else 0,
        "max_trace_len": max(lengths) if lengths else 0,
        "mean_trace_len": round(mean_len, 3),
        "normalized_path": str(out_path),
    }
    print(f"  {corpus_name}: {len(valid_traces)} traces, alphabet={len(alphabet)}, events={num_events_total}")
    return record


def main():
    parser = argparse.ArgumentParser(
        description="Normalize raw trace corpora to Texada format and build manifest."
    )
    parser.add_argument("--input-dir", default="data/raw", help="Raw data directory (default: data/raw)")
    parser.add_argument("--output-dir", default="data/normalized", help="Output directory (default: data/normalized)")
    parser.add_argument("--corpus", default=None, help="Normalize only this corpus (default: all)")
    args = parser.parse_args()

    raw_dir = Path(args.input_dir)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = Path("data/manifest.json")

    if args.corpus:
        corpora = [args.corpus]
    else:
        # Discover from raw dir
        corpora = [d.name for d in sorted(raw_dir.iterdir()) if d.is_dir()]
        if not corpora:
            print("No corpus subdirectories found in", raw_dir)
            return

    print(f"Normalizing {len(corpora)} corpus(es)...")

    # Load existing manifest if present
    existing_manifest: dict[str, dict] = {}
    if manifest_path.exists():
        for entry in json.loads(manifest_path.read_text(encoding="utf-8")):
            existing_manifest[entry["name"]] = entry

    for name in corpora:
        print(f"\n[{name}]")
        try:
            record = normalize_corpus(name, raw_dir, out_dir)
            existing_manifest[name] = record
        except FileNotFoundError as e:
            print(f"  [SKIP] {e}")

    # Write manifest
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_list = list(existing_manifest.values())
    manifest_path.write_text(json.dumps(manifest_list, indent=2), encoding="utf-8")
    print(f"\nManifest written to {manifest_path}")
    print("Done.")


if __name__ == "__main__":
    main()
