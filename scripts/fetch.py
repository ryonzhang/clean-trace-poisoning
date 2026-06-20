#!/usr/bin/env python3
"""fetch.py — Download and generate raw trace corpora for cleantrace-data.

Usage:
    py scripts/fetch.py [--seed 42] [--output-dir data/raw] [--skip-network]
"""

import argparse
import hashlib
import json
import random
import sys
import time
from pathlib import Path

import requests
from tqdm import tqdm


# ── helpers ──────────────────────────────────────────────────────────────────

def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def write_traces(path: Path, traces: list[list[str]]) -> None:
    """Write traces in Texada format: events one per line, blank line between traces."""
    lines = []
    for trace in traces:
        lines.extend(trace)
        lines.append("")          # blank line separator
    path.write_text("\n".join(lines), encoding="utf-8")


def read_texada(path: Path) -> list[list[str]]:
    """Parse Texada format into list of event lists."""
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


# ── corpus 1: texada-bundled ──────────────────────────────────────────────────

TEXADA_BASE = "https://raw.githubusercontent.com/ModelInference/texada/master/traces/"
TEXADA_FILES = ["login.txt", "example2.txt", "mult-trace.txt"]

TEXADA_FALLBACKS = {
    "login.txt": """\
login
logout

login
fail

login
logout

""",
    "example2.txt": """\
a
b
c

a
c

b
c

""",
    "mult-trace.txt": """\
a
b
a
b

b
a
b

a
a
b

""",
}


def fetch_texada(out_dir: Path, skip_network: bool) -> list[Path]:
    dest_dir = out_dir / "texada-bundled"
    dest_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for fname in TEXADA_FILES:
        dest = dest_dir / fname
        if dest.exists():
            print(f"  [cache] {fname}")
            paths.append(dest)
            continue
        if skip_network:
            print(f"  [skip-network] writing fallback for {fname}")
            dest.write_text(TEXADA_FALLBACKS[fname], encoding="utf-8")
        else:
            url = TEXADA_BASE + fname
            try:
                r = requests.get(url, timeout=15)
                r.raise_for_status()
                dest.write_text(r.text, encoding="utf-8")
                print(f"  [OK] {url}")
            except Exception as exc:
                print(f"  [WARN] {url}: {exc} — using fallback")
                dest.write_text(TEXADA_FALLBACKS[fname], encoding="utf-8")
        paths.append(dest)
    return paths


# ── corpus 2: crv2014 ─────────────────────────────────────────────────────────

CRV2014_URL = "https://www.react.uni-saarland.de/tools/crv2014/"

def fetch_crv2014(out_dir: Path, skip_network: bool, rng: random.Random, sources_path: Path) -> Path:
    dest_dir = out_dir / "crv2014"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "crv2014_traces.txt"
    if dest.exists():
        print("  [cache] crv2014_traces.txt")
        return dest

    skipped = False
    if not skip_network:
        try:
            r = requests.get(CRV2014_URL, timeout=15)
            r.raise_for_status()
            # Page exists but actual trace files need individual download — mark SKIPPED
            skipped = True
            print(f"  [SKIP] CRV2014: trace files not directly parseable from index page — generating synthetic fallback")
        except Exception as exc:
            skipped = True
            print(f"  [SKIP] CRV2014 fetch failed ({exc}) — generating synthetic fallback")
    else:
        skipped = True
        print("  [skip-network] CRV2014 — generating synthetic fallback")

    if skipped:
        # Log to SOURCES.md
        sources_text = sources_path.read_text(encoding="utf-8") if sources_path.exists() else ""
        if "CRV2014_STATUS" not in sources_text:
            with open(sources_path, "a", encoding="utf-8") as f:
                f.write(f"\n\n## CRV2014_STATUS\nSKIPPED at fetch time. Synthetic fallback generated.\n")
        # Generate synthetic fallback with CRV-like events
        alphabet = ["req", "ack", "data", "fin", "rst", "syn"]
        traces = _gen_traces(rng, alphabet, n=200, min_len=5, max_len=18)
        write_traces(dest, traces)
        print(f"  [synthetic-fallback] crv2014: {len(traces)} traces")
    return dest


# ── corpus 3: dacapo-synth ────────────────────────────────────────────────────

def _gen_traces(rng: random.Random, alphabet: list[str], n: int, min_len: int, max_len: int) -> list[list[str]]:
    return [
        [rng.choice(alphabet) for _ in range(rng.randint(min_len, max_len))]
        for _ in range(n)
    ]


def gen_dacapo_synth(out_dir: Path, rng: random.Random) -> Path:
    """Instrument-style synthetic traces: function entry/exit events."""
    dest_dir = out_dir / "dacapo-synth"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "dacapo_synth.txt"
    if dest.exists():
        print("  [cache] dacapo_synth.txt")
        return dest

    routines = ["fibonacci", "sort", "search", "merge", "quicksort", "bsearch", "heapsort"]
    # Build traces by simulating call sequences with enter/exit pairs
    traces = []
    for _ in range(250):
        trace = []
        depth = []
        n_calls = rng.randint(3, 12)
        for _ in range(n_calls):
            routine = rng.choice(routines)
            trace.append(f"{routine}.enter")
            depth.append(routine)
            # sometimes nest
            if rng.random() < 0.4 and depth:
                inner = rng.choice(routines)
                trace.append(f"{inner}.enter")
                trace.append(f"{inner}.exit")
            trace.append(f"{depth.pop()}.exit")
        traces.append(trace)

    write_traces(dest, traces)
    print(f"  [generated] dacapo-synth: {len(traces)} traces")
    return dest


# ── corpus 4: fsm-generated ───────────────────────────────────────────────────

def gen_fsm_traces(out_dir: Path, rng: random.Random) -> Path:
    dest_dir = out_dir / "fsm-generated"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "fsm_generated.txt"
    if dest.exists():
        print("  [cache] fsm_generated.txt")
        return dest

    # FSM 1: request-response protocol
    # States: IDLE -> (REQ) -> PENDING -> (ACK) -> ACTIVE -> (RESP) -> IDLE  | ACTIVE -> (END) -> IDLE
    def fsm_request_response(rng):
        trace = []
        state = "IDLE"
        for _ in range(rng.randint(1, 5)):
            if state == "IDLE":
                trace.append("REQ"); state = "PENDING"
            elif state == "PENDING":
                trace.append("ACK"); state = "ACTIVE"
            elif state == "ACTIVE":
                if rng.random() < 0.7:
                    trace.append("RESP"); state = "IDLE"
                else:
                    trace.append("END"); state = "IDLE"
        return trace

    # FSM 2: lock-unlock
    # States: UNLOCKED -> (LOCK) -> LOCKED -> (UNLOCK) -> UNLOCKED
    # Also: LOCKED -> (TRY_LOCK) -> LOCKED (fail), UNLOCKED -> (TRY_UNLOCK) -> UNLOCKED (fail)
    def fsm_lock_unlock(rng):
        trace = []
        state = "UNLOCKED"
        for _ in range(rng.randint(2, 10)):
            if state == "UNLOCKED":
                if rng.random() < 0.8:
                    trace.append("LOCK"); state = "LOCKED"
                else:
                    trace.append("TRY_UNLOCK"); # noop
            elif state == "LOCKED":
                if rng.random() < 0.7:
                    trace.append("UNLOCK"); state = "UNLOCKED"
                else:
                    trace.append("TRY_LOCK"); # already locked
        return trace if trace else ["LOCK", "UNLOCK"]

    # FSM 3: open-read-write-close
    # States: CLOSED -> (OPEN) -> OPEN_RD -> (READ|WRITE)* -> (CLOSE) -> CLOSED
    def fsm_open_close(rng):
        trace = []
        state = "CLOSED"
        for _ in range(rng.randint(1, 4)):
            if state == "CLOSED":
                trace.append("OPEN"); state = "OPEN_RD"
            elif state == "OPEN_RD":
                n_ops = rng.randint(1, 6)
                for _ in range(n_ops):
                    trace.append(rng.choice(["READ", "WRITE", "SEEK", "STAT"]))
                trace.append("CLOSE"); state = "CLOSED"
        return trace if trace else ["OPEN", "READ", "CLOSE"]

    fsm_generators = [fsm_request_response, fsm_lock_unlock, fsm_open_close]
    traces = []
    for _ in range(300):
        gen = rng.choice(fsm_generators)
        t = gen(rng)
        if t:
            traces.append(t)

    write_traces(dest, traces)
    print(f"  [generated] fsm-generated: {len(traces)} traces")
    return dest


# ── corpus 5: posix-syscall ───────────────────────────────────────────────────

def gen_posix_syscall(out_dir: Path, rng: random.Random) -> Path:
    dest_dir = out_dir / "posix-syscall"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "posix_syscall.txt"
    if dest.exists():
        print("  [cache] posix_syscall.txt")
        return dest

    # Simulated POSIX syscall sequences
    # Patterns: file I/O, process, network, memory
    file_io = ["open", "read", "write", "lseek", "fstat", "close"]
    process_ops = ["fork", "exec", "wait", "exit", "getpid", "getppid", "signal"]
    network_ops = ["socket", "bind", "listen", "accept", "connect", "send", "recv", "shutdown"]
    mem_ops = ["mmap", "munmap", "mprotect", "mlock", "munlock"]

    # Build plausible sequences
    def file_sequence(rng):
        t = ["open"]
        n = rng.randint(1, 8)
        for _ in range(n):
            t.append(rng.choice(["read", "write", "lseek", "fstat"]))
        t.append("close")
        return t

    def process_sequence(rng):
        t = []
        if rng.random() < 0.5:
            t.append("fork")
            t.append(rng.choice(["exec", "getpid"]))
            t.append("wait")
            t.append("exit")
        else:
            for _ in range(rng.randint(2, 6)):
                t.append(rng.choice(process_ops))
        return t if t else ["getpid", "exit"]

    def net_sequence(rng):
        if rng.random() < 0.5:
            # server
            t = ["socket", "bind", "listen", "accept"]
            for _ in range(rng.randint(1, 4)):
                t.append(rng.choice(["send", "recv"]))
            t.append("shutdown")
        else:
            # client
            t = ["socket", "connect"]
            for _ in range(rng.randint(1, 4)):
                t.append(rng.choice(["send", "recv"]))
            t.append("shutdown")
        return t

    def mem_sequence(rng):
        t = ["mmap"]
        for _ in range(rng.randint(0, 3)):
            t.append(rng.choice(["mprotect", "mlock"]))
        t.append("munmap")
        return t

    generators = [file_sequence, process_sequence, net_sequence, mem_sequence]
    traces = []
    for _ in range(250):
        gen = rng.choice(generators)
        t = gen(rng)
        if t:
            traces.append(t)

    write_traces(dest, traces)
    print(f"  [generated] posix-syscall: {len(traces)} traces")
    return dest


# ── SHA256 registry ──────────────────────────────────────────────────────────

def update_sha256(out_dir: Path, paths: list[Path]) -> None:
    sums_path = out_dir / "sha256sums.txt"
    existing = {}
    if sums_path.exists():
        for line in sums_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "  " in line:
                digest, rel = line.split("  ", 1)
                existing[rel] = digest

    for p in paths:
        rel = str(p.relative_to(out_dir))
        existing[rel] = sha256_of_file(p)

    with open(sums_path, "w", encoding="utf-8") as f:
        for rel, digest in sorted(existing.items()):
            f.write(f"{digest}  {rel}\n")
    print(f"\nSHA256 sums written to {sums_path}")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Fetch and generate raw trace corpora for cleantrace-data."
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    parser.add_argument("--output-dir", default="data/raw", help="Output directory (default: data/raw)")
    parser.add_argument("--skip-network", action="store_true", help="Skip all network requests; use cache/fallbacks only")
    args = parser.parse_args()

    print(f"Seed: {args.seed}")
    rng = random.Random(args.seed)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    sources_path = out_dir / "SOURCES.md"

    all_paths: list[Path] = []

    print("\n[1/5] texada-bundled")
    paths = fetch_texada(out_dir, args.skip_network)
    all_paths.extend(paths)

    print("\n[2/5] crv2014")
    p = fetch_crv2014(out_dir, args.skip_network, rng, sources_path)
    all_paths.append(p)

    print("\n[3/5] dacapo-synth")
    p = gen_dacapo_synth(out_dir, rng)
    all_paths.append(p)

    print("\n[4/5] fsm-generated")
    p = gen_fsm_traces(out_dir, rng)
    all_paths.append(p)

    print("\n[5/5] posix-syscall")
    p = gen_posix_syscall(out_dir, rng)
    all_paths.append(p)

    print("\nUpdating SHA256 sums...")
    update_sha256(out_dir, all_paths)

    print("\nDone. Raw corpora written to:", out_dir.resolve())


if __name__ == "__main__":
    main()
