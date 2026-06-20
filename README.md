# Clean-Trace Poisoning of LTL Specification Miners — Artifact

This artifact accompanies the FPS 2026 submission *"Clean-Trace Poisoning: Deleting Safety
Properties from Specification Miners with Individually-Legal Executions"*. We demonstrate
that an adversary controlling a fraction of the trace-collection infrastructure can inject
semantically valid (non-anomalous) execution traces that silently suppress target safety
properties from the Texada LTL miner, without triggering per-sample outlier detectors. We
prove a closed-form deletion budget, show it is tight via a quorum-provenance defense, and
characterize the stealth–margin trade-off empirically on two real-execution corpora.

---

## Reproduce in 3 commands

```bash
pip install -r requirements.txt
python3 experiments/run_all.py
python3 experiments/run_extended.py && python3 experiments/run_nontransfer.py && python3 experiments/run_stealth_margin.py
```

---

## Repository layout

```
cleantrace-data/
├── scripts/
│   ├── fetch.py                      # Download / generate raw corpora
│   ├── normalize.py                  # Convert to Texada one-event-per-line format
│   ├── validate.py                   # Check normalized files, manifest, SHA256s
│   ├── mine_baseline.py              # Dwyer-pattern LTL mining (built-in scanner)
│   ├── extract_legal_poison_pool.py  # Extract antecedent-only traces for poison pool
│   ├── tag_provenance.py             # Assign source_id per trace; mark compromised
│   ├── gen_params_grid.py            # Generate data/params_grid.csv
│   ├── gen_real_syscall.py           # (Linux only) Re-trace programs via strace
│   └── gen_real_network.py           # (Linux only) Re-trace network programs via strace
├── experiments/
│   ├── run_all.py                    # Main attack + bound + detectability + defense
│   ├── run_extended.py               # Multi-source (Thm 2), budget landscape, threshold sweep
│   ├── run_nontransfer.py            # IsolationForest/LOF non-transfer defense
│   └── run_stealth_margin.py         # Stealth vs. confidence-margin characterization
├── data/
│   ├── normalized/                   # Texada-format corpora (canonical artifact)
│   │   ├── real-syscall.txt          # Real strace traces — file-descriptor lifecycle
│   │   └── real-network.txt          # Real strace traces — socket lifecycle
│   ├── baseline/                     # Mined LTL property CSVs
│   ├── provenance/                   # JSONL {trace_id, source_id, events, compromised}
│   ├── poison_pool/                  # Legal antecedent-only traces per target property
│   ├── raw/                          # Raw strace files + SOURCES.md + sha256sums.txt
│   ├── extra/                        # Synthetic corpora NOT used in the paper
│   ├── manifest.json                 # Per-corpus statistics
│   └── params_grid.csv               # 1215-row parameter sweep grid
├── results/                          # Pre-computed outputs (see Results map below)
├── figures/                          # Pre-computed figures
├── paper/
│   ├── main.tex                      # Submission source (anonymous)
│   └── PAPER_README.md               # How to compile (Overleaf + official llncs.cls)
├── templates/
│   └── dwyer_patterns.txt            # 8 Dwyer LTL property-pattern templates
├── Makefile
├── requirements.txt
└── LICENSE
```

---

## Results map

| Script | Paper items produced |
|---|---|
| `experiments/run_all.py` | Tables 1–3 (attack, cross-corpus, defense), Fig 1–2 inputs, `results/summary.json`, `results/attack_results.csv`, `results/defense_results.csv` |
| `experiments/run_nontransfer.py` | "Non-transfer" figure, `results/nontransfer.csv` |
| `experiments/run_extended.py` | Threshold sweep, budget landscape, multi-source (Thm 2) tables/figure, `results/threshold_sweep.csv`, `results/budget_landscape.csv`, `results/multisource.csv` |
| `experiments/run_stealth_margin.py` | Stealth-vs-margin figure, `results/stealth_margin.csv` |

---

## Data provenance

The two corpora used in the paper (`real-syscall`, `real-network`) are **constructed
benchmarks of real program executions**:

- **Collection method:** `strace -e trace=file,network` on a mix of standard Linux programs
  (`cat`, `grep`, `wc`, `curl`, `wget`, `python3`, small C programs). Each program run
  produces one raw strace file; the syscall/network-event tokens are extracted and
  normalized to Texada format.
- **Corpus construction:** the program mix was chosen deliberately. A *leak program*
  (one that calls `open` without a matching `close`, or `connect` without a matching
  `close`) is included. The number of leak-program runs was tuned so the target property
  `G(open → F(close))` / `G(connect → F(close))` sits just above the mining threshold
  θ = 0.9 in the clean corpus — this is the "fragile but valid" starting condition the
  attack exploits.
- **Source attribution:** each trace is assigned a `source_id` equal to the producing
  program name (e.g. `cat`, `curl`). Provenance JSONL files in `data/provenance/` record
  per-trace source and whether that source is marked compromised in a given scenario.
- **Sanitization:** environment-specific paths in raw strace files (e.g. session
  temp-directory paths) are redacted to `/home/user/REDACTED`. Only the event-token
  sequences matter; absolute paths are not part of the corpus alphabet.

The committed normalized files in `data/normalized/` **are the canonical artifact**.
Running `gen_real_syscall.py` / `gen_real_network.py` re-instruments live programs on the
host and will produce a **different corpus** (syscall sequences depend on the host OS,
library versions, and filesystem layout). Regeneration is provided for transparency and
inspection only — it will NOT reproduce the paper's exact numbers. These generators require
Linux with `strace`, `gcc`, `curl`, `wget`, `nc`, and `ssh`.

Synthetic and auxiliary corpora are in `data/extra/` with a README; they are **not** used
in any paper experiment.

---

## Texada trace format

One event token per line; a blank line separates traces:

```
open
read
close

open
write
close

```

To run Texada manually (if installed):

```bash
texada --log data/normalized/real-syscall.txt \
       --property-type "G(a -> F(b))" \
       --threshold 0.9
```

---

## Reproducibility notes

- All scripts use `--seed 42` by default. Given the same seed and Python ≥ 3.10 environment,
  all splits and sweep results are deterministic from the committed normalized corpora.
- `python3 scripts/validate.py` verifies SHA256 checksums, manifest counts, and normalized
  file integrity. It will report 2 expected FAIL on empty baseline CSVs (synthetic corpora
  in `data/extra/` have fewer traces than the 0.9 threshold requires).
- Pre-computed results in `results/` and figures in `figures/` are provided so reviewers
  can inspect outputs without running experiments.
