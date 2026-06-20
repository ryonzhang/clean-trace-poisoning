# Clean-Trace Poisoning — Experimental Results

**Corpus:** `real-syscall` — 98 *real* `strace` traces from live Linux programs
(coreutils, Python, a native fd-leak program). 12 native provenance sources.
**Target property:** `G(open → F(close))` (every opened descriptor is eventually
closed — the textbook resource-safety property). **Threshold θ = 0.9.**
All poison traces are *real, individually-legal* fd-leak executions drawn from a
held-out split — no synthesis, no perturbation.

## 1. Attack
Baseline confidence of the target = **0.918** (90/98). Injecting legal
antecedent-only (open-without-close) traces deletes it at **K = 3 traces (3.1 %
of the corpus).** Each poison trace is a behavior real programs exhibit, so no
per-sample filter can flag it.

## 2. Budget bound (foundation)
Closed form: poison fixes nsat = S₀ and grows nant, so deletion occurs when
`K > S₀/θ − A₀`, i.e. **K\* = ⌊S₀/θ − A₀⌋ + 1 = 3**.
Empirical minimum deletion budget = **3**. **Bound matches exactly.**

## 3. Detectability (stealth)
| metric | baseline | after attack |
|---|---|---|
| properties mined | 48 | 44 |
| mean confidence (whole spec) | 0.982 | 0.988 |

Only the descriptor-close safety family is removed
(`open→F(close)`, `read→F(close)`, `mmap→F(close)`, `open→F(stat)`) — a coherent
fd-leak monitoring blind spot — while global spec health is flat (Δ mean
confidence = +0.006, property count −4 of 48). The induced confidence shift
(0.0273) is **0.98σ** of the corpus's natural bootstrap resampling variance
(σ = 0.0278): the attack hides inside ordinary sampling noise.

## 4. Provenance-quorum defense
Count support per native source; retain a property only if ≥ q sources witness
it at θ. The target holds in **11/12** clean sources (only the `leak` source
fails); the attacker is a single extra non-supporting source, so supporting
sources stay at 11.

| q | target recovered | false-positive rate | certified max compromised sources |
|---|---|---|---|
| 2 | yes | 0.00 | 9 |
| 3 | yes | 0.10 | 8 |
| 5 | yes | 0.27 | 6 |
| 9 | yes | 0.40 | 2 |
| 12 | no | 0.63 | 0 |

**Sweet spot q = 2:** the deleted property family is fully recovered with **zero
false positives**, at **1.33× counting overhead**. Increasing q raises the
certified resilience but drops legitimate rare-antecedent properties — the
predicted cost. **Certified survival bound:** the target survives if the number
of compromised sources ≤ `S_clean − q = 11 − q`.

## Takeaway
A 3-trace, 3 %, individually-legal injection silently deletes a resource-safety
property while the monitor looks healthy; the closed-form budget predicts it
exactly; and provenance-quorum counting recovers it with zero false positives at
low quorum. Attack + bound + defense, all on real syscall traces.
