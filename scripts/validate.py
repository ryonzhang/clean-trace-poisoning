#!/usr/bin/env python3
"""validate.py — Validate normalized corpora, manifest, and checksums.

Usage:
    py scripts/validate.py [--normalized-dir data/normalized] [--raw-dir data/raw]
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


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


def check_normalized_files(norm_dir: Path) -> tuple[int, int, list[str]]:
    passed, failed, msgs = 0, 0, []
    files = sorted(norm_dir.glob("*.txt"))
    if not files:
        msgs.append(f"FAIL: no .txt files in {norm_dir}")
        failed += 1
        return passed, failed, msgs

    for f in files:
        try:
            traces = read_texada(f)
            bad = [i for i, t in enumerate(traces) if not t]
            if bad:
                msgs.append(f"FAIL [{f.name}]: {len(bad)} empty traces at indices {bad[:5]}")
                failed += 1
            else:
                msgs.append(f"PASS [{f.name}]: {len(traces)} traces, all non-empty")
                passed += 1
        except Exception as e:
            msgs.append(f"FAIL [{f.name}]: parse error: {e}")
            failed += 1

    return passed, failed, msgs


def check_manifest(manifest_path: Path, norm_dir: Path) -> tuple[int, int, list[str]]:
    passed, failed, msgs = 0, 0, []
    if not manifest_path.exists():
        msgs.append(f"FAIL: manifest not found at {manifest_path}")
        failed += 1
        return passed, failed, msgs

    try:
        entries = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        msgs.append(f"FAIL: manifest JSON parse error: {e}")
        failed += 1
        return passed, failed, msgs

    msgs.append(f"PASS: manifest JSON parses OK ({len(entries)} entries)")
    passed += 1

    for entry in entries:
        name = entry.get("name", "?")
        norm_path = norm_dir / f"{name}.txt"
        if not norm_path.exists():
            msgs.append(f"FAIL [manifest/{name}]: normalized file not found: {norm_path}")
            failed += 1
            continue
        actual_traces = read_texada(norm_path)
        declared = entry.get("num_traces", -1)
        if len(actual_traces) != declared:
            msgs.append(f"FAIL [manifest/{name}]: declared {declared} traces, found {len(actual_traces)}")
            failed += 1
        else:
            msgs.append(f"PASS [manifest/{name}]: trace count matches ({declared})")
            passed += 1

    return passed, failed, msgs


def check_sha256sums(raw_dir: Path) -> tuple[int, int, list[str]]:
    passed, failed, msgs = 0, 0, []
    sums_path = raw_dir / "sha256sums.txt"
    if not sums_path.exists():
        msgs.append(f"FAIL: sha256sums.txt not found at {sums_path}")
        failed += 1
        return passed, failed, msgs

    lines = sums_path.read_text(encoding="utf-8").splitlines()
    for line in lines:
        line = line.strip()
        if not line or "  " not in line:
            continue
        expected, rel = line.split("  ", 1)
        fpath = raw_dir / rel
        if not fpath.exists():
            msgs.append(f"FAIL [sha256/{rel}]: file not found")
            failed += 1
            continue
        actual = sha256_of_file(fpath)
        if actual == expected:
            msgs.append(f"PASS [sha256/{rel}]: checksum matches")
            passed += 1
        else:
            msgs.append(f"FAIL [sha256/{rel}]: expected {expected}, got {actual}")
            failed += 1

    if not lines:
        msgs.append("WARN: sha256sums.txt is empty")

    return passed, failed, msgs


def check_baseline(baseline_dir: Path) -> tuple[int, int, list[str]]:
    passed, failed, msgs = 0, 0, []
    if not baseline_dir.exists():
        msgs.append(f"INFO: baseline dir {baseline_dir} does not exist (run mine_baseline.py first) — SKIP")
        return passed, failed, msgs

    csvs = sorted(baseline_dir.glob("*.csv"))
    if not csvs:
        msgs.append(f"INFO: no .csv files in {baseline_dir} — SKIP")
        return passed, failed, msgs

    for f in csvs:
        content = f.read_text(encoding="utf-8").strip()
        if not content or len(content.splitlines()) < 2:
            msgs.append(f"FAIL [baseline/{f.name}]: file is empty or has no data rows")
            failed += 1
        else:
            msgs.append(f"PASS [baseline/{f.name}]: non-empty ({len(content.splitlines())} lines)")
            passed += 1

    return passed, failed, msgs


def main():
    parser = argparse.ArgumentParser(
        description="Validate normalized corpora, manifest, and checksums."
    )
    parser.add_argument("--normalized-dir", default="data/normalized", help="Normalized data directory")
    parser.add_argument("--raw-dir", default="data/raw", help="Raw data directory")
    parser.add_argument("--baseline-dir", default="data/baseline", help="Baseline CSV directory")
    args = parser.parse_args()

    norm_dir = Path(args.normalized_dir)
    raw_dir = Path(args.raw_dir)
    baseline_dir = Path(args.baseline_dir)
    manifest_path = Path("data/manifest.json")

    total_passed, total_failed = 0, 0
    all_sections = []

    print("=" * 60)
    print("CHECK 1: Normalized files parse correctly")
    print("-" * 60)
    p, f, msgs = check_normalized_files(norm_dir)
    for m in msgs:
        print(" ", m)
    total_passed += p; total_failed += f
    all_sections.append(("Normalized files", p, f))

    print()
    print("=" * 60)
    print("CHECK 2: Manifest consistency")
    print("-" * 60)
    p, f, msgs = check_manifest(manifest_path, norm_dir)
    for m in msgs:
        print(" ", m)
    total_passed += p; total_failed += f
    all_sections.append(("Manifest", p, f))

    print()
    print("=" * 60)
    print("CHECK 3: SHA256 checksums")
    print("-" * 60)
    p, f, msgs = check_sha256sums(raw_dir)
    for m in msgs:
        print(" ", m)
    total_passed += p; total_failed += f
    all_sections.append(("SHA256", p, f))

    print()
    print("=" * 60)
    print("CHECK 4: Baseline CSVs (if present)")
    print("-" * 60)
    p, f, msgs = check_baseline(baseline_dir)
    for m in msgs:
        print(" ", m)
    total_passed += p; total_failed += f
    all_sections.append(("Baseline CSVs", p, f))

    print()
    print("=" * 60)
    print("SUMMARY")
    print("-" * 60)
    for section, p, f in all_sections:
        status = "PASS" if f == 0 else "FAIL"
        print(f"  [{status}] {section}: {p} passed, {f} failed")
    print(f"\n  Total: {total_passed} passed, {total_failed} failed")
    print("=" * 60)

    sys.exit(1 if total_failed > 0 else 0)


if __name__ == "__main__":
    main()
