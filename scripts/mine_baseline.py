#!/usr/bin/env python3
"""mine_baseline.py — Mine LTL property baselines from normalized trace corpora.

If Texada binary is available, delegates to it. Otherwise computes property
statistics directly from traces (simulated mining).

Usage:
    py scripts/mine_baseline.py --corpus dacapo-synth [--texada-bin texada] [--threshold 0.9]
    py scripts/mine_baseline.py --all-corpora
"""

import argparse
import csv
import itertools
import json
import shutil
import subprocess
import sys
from pathlib import Path


# ── Texada format parser ──────────────────────────────────────────────────────

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


# ── Property checkers (simulated mining) ─────────────────────────────────────

def check_response(trace: list[str], a: str, b: str) -> tuple[bool, bool]:
    """G(a -> F(b)): every a is eventually followed by b.
    Returns (antecedent_present, property_satisfied)."""
    indices_a = [i for i, e in enumerate(trace) if e == a]
    if not indices_a:
        return False, True  # vacuously true, no antecedent
    for i in indices_a:
        if b not in trace[i:]:
            return True, False  # a occurs but b never follows
    return True, True


def check_absence(trace: list[str], a: str, b: str = "") -> tuple[bool, bool]:
    """G(!a): a never occurs."""
    # antecedent is always True (universe)
    return True, (a not in trace)


def check_universality(trace: list[str], a: str, b: str = "") -> tuple[bool, bool]:
    """G(a): a always occurs (at least once)."""
    return True, (a in trace)


def check_precedence(trace: list[str], a: str, b: str) -> tuple[bool, bool]:
    """G(b -> O(a)): every b is preceded by some a.
    Returns (antecedent_present, property_satisfied)."""
    if b not in trace:
        return False, True
    for i, e in enumerate(trace):
        if e == b:
            if a not in trace[:i]:
                return True, False
    return True, True


def check_chain_response(trace: list[str], a: str, b: str) -> tuple[bool, bool]:
    """G(a -> X(b)): every a is immediately followed by b."""
    if a not in trace:
        return False, True
    for i, e in enumerate(trace[:-1]):
        if e == a and trace[i + 1] != b:
            return True, False
    # last element: if it's a, no successor
    if trace and trace[-1] == a:
        return True, False
    return True, True


def check_alt_response(trace: list[str], a: str, b: str) -> tuple[bool, bool]:
    """G(a -> X(!a U b)): alternating response — after a, b occurs before next a."""
    if a not in trace:
        return False, True
    i = 0
    antecedent_seen = False
    while i < len(trace):
        if trace[i] == a:
            antecedent_seen = True
            # find b before next a
            j = i + 1
            found_b = False
            while j < len(trace):
                if trace[j] == b:
                    found_b = True
                    break
                if trace[j] == a:
                    break
                j += 1
            if not found_b:
                return True, False
            i = j + 1
        else:
            i += 1
    return antecedent_seen, True


def check_chain_precedence(trace: list[str], a: str, b: str) -> tuple[bool, bool]:
    """G(X(b) -> a): b is always directly preceded by a."""
    if b not in trace:
        return False, True
    for i in range(1, len(trace)):
        if trace[i] == b and trace[i - 1] != a:
            return True, False
    if trace and trace[0] == b:
        return True, False
    return True, True


TEMPLATES = {
    "RESPONSE":       (check_response,        "G({a} -> F({b}))",      True),   # (fn, formula, needs_b)
    "ABSENCE":        (check_absence,          "G(!{a})",                False),
    "UNIVERSALITY":   (check_universality,     "G({a})",                 False),
    "PRECEDENCE":     (check_precedence,       "G({b} -> O({a}))",       True),
    "CHAIN_RESPONSE": (check_chain_response,   "G({a} -> X({b}))",       True),
    "ALT_RESPONSE":   (check_alt_response,     "G({a} -> X((!{a}) U ({b})))", True),
    "CHAIN_PRECEDE":  (check_chain_precedence, "G(X({b}) -> {a})",       True),
}


# ── Simulated mining ──────────────────────────────────────────────────────────

def mine_simulated(traces: list[list[str]], threshold: float, min_nant: int = 5) -> list[dict]:
    alphabet = sorted({e for t in traces for e in t})
    results = []

    total_traces = len(traces)

    for tname, (fn, formula_tpl, needs_b) in TEMPLATES.items():
        if needs_b:
            pairs = [(a, b) for a, b in itertools.product(alphabet, alphabet) if a != b]
        else:
            pairs = [(a, "") for a in alphabet]

        for a, b in pairs:
            nant = 0
            nsat = 0
            for trace in traces:
                ant, sat = fn(trace, a, b)
                if ant:
                    nant += 1
                    if sat:
                        nsat += 1

            if nant < min_nant:
                continue
            confidence = nsat / nant
            if confidence < threshold:
                continue

            formula = formula_tpl.replace("{a}", a).replace("{b}", b)
            ant_freq = nant / total_traces
            if ant_freq < 0.1:
                bucket = "low(<0.1)"
            elif ant_freq < 0.3:
                bucket = "medium(0.1-0.3)"
            else:
                bucket = "high(>0.3)"

            results.append({
                "property_instance": formula,
                "template": tname,
                "event_a": a,
                "event_b": b,
                "nsat": nsat,
                "nant": nant,
                "confidence": round(confidence, 6),
                "antecedent_frequency": round(ant_freq, 6),
                "threshold_margin": round(confidence - threshold, 6),
            })

    return results


# ── Texada runner ─────────────────────────────────────────────────────────────

def mine_texada(texada_bin: str, traces_path: Path, threshold: float) -> list[dict] | None:
    """Try to run Texada; return None if unavailable."""
    if not shutil.which(texada_bin) and not Path(texada_bin).is_file():
        return None
    try:
        cmd = [texada_bin, "--log-file", str(traces_path), "--linear-fast-synth",
               "--support", str(threshold)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            print(f"  [warn] Texada exited {result.returncode}: {result.stderr[:200]}")
            return None
        # Parse output (Texada prints property lines)
        rows = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                rows.append({"property_instance": line, "template": "TEXADA", "event_a": "",
                             "event_b": "", "nsat": "", "nant": "", "confidence": "",
                             "antecedent_frequency": "", "threshold_margin": ""})
        return rows
    except Exception as e:
        print(f"  [warn] Texada execution failed: {e}")
        return None


# ── Main ──────────────────────────────────────────────────────────────────────

def process_corpus(corpus_name: str, norm_dir: Path, out_dir: Path,
                   texada_bin: str, threshold: float, seed: int) -> None:
    traces_path = norm_dir / f"{corpus_name}.txt"
    if not traces_path.exists():
        print(f"  [SKIP] {corpus_name}: normalized file not found at {traces_path}")
        return

    traces = read_texada(traces_path)
    print(f"  Loaded {len(traces)} traces from {traces_path.name}")

    # Try Texada first
    rows = mine_texada(texada_bin, traces_path, threshold)
    if rows is not None:
        print(f"  [Texada] mined {len(rows)} properties")
    else:
        print(f"  [simulated] Texada not found at '{texada_bin}' — using built-in property scanner")
        rows = mine_simulated(traces, threshold)
        print(f"  [simulated] found {len(rows)} properties above threshold={threshold}")

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{corpus_name}.csv"

    fieldnames = ["property_instance", "template", "event_a", "event_b",
                  "nsat", "nant", "confidence", "antecedent_frequency", "threshold_margin"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"  Wrote {len(rows)} rows to {out_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Mine LTL property baselines from normalized trace corpora."
    )
    parser.add_argument("--corpus", default=None, help="Corpus name (e.g. dacapo-synth)")
    parser.add_argument("--all-corpora", action="store_true", help="Process all corpora in normalized dir")
    parser.add_argument("--texada-bin", default="texada", help="Path to Texada binary (default: texada)")
    parser.add_argument("--threshold", type=float, default=0.9, help="Confidence threshold (default: 0.9)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    parser.add_argument("--norm-dir", default="data/normalized", help="Normalized data directory")
    parser.add_argument("--output-dir", default="data/baseline", help="Output directory for CSVs")
    args = parser.parse_args()

    norm_dir = Path(args.norm_dir)
    out_dir = Path(args.output_dir)

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
        process_corpus(corpus, norm_dir, out_dir, args.texada_bin, args.threshold, args.seed)

    print("\nDone.")


if __name__ == "__main__":
    main()
