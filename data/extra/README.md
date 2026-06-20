# Synthetic / Auxiliary Corpora

The files in this directory are **synthetic or auxiliary corpora** not used in the paper's
evaluation. They are retained for completeness and future use.

| Corpus | Type | Note |
|---|---|---|
| crv2014 | Synthetic fallback | CRV 2014 site unreachable at collection time; replaced by synthetic |
| dacapo-synth | Synthetic | Instrumented Python routines |
| fsm-generated | Synthetic | 3 hand-coded FSMs (request/lock/file) |
| posix-syscall | Synthetic | Simulated POSIX call sequences |
| texada-bundled | Reference | Texada GitHub test suite (MIT) |

The paper's experiments use **only** `data/normalized/real-syscall.txt` and
`data/normalized/real-network.txt`.
