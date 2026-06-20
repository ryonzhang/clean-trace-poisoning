#!/usr/bin/env python3
"""run_all.py — Clean-trace poisoning experiments on REAL corpora.

Runs the full attack -> budget-bound -> detectability -> provenance-quorum-defense
pipeline on each configured corpus and aggregates results.

Corpora:
  real-syscall : target G(open -> F(close))     [file-descriptor lifecycle]
  real-network : target G(connect -> F(close))  [socket lifecycle]
"""
import sys, json, csv, math, random, statistics, time, os
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, "scripts")
import mine_baseline as mb

THETA = 0.9
CFGS = [
    dict(name="real-syscall", a="open", b="close",
         pool="data/poison_pool/real-syscall_open_close_pool.txt",
         prov="data/provenance/real-syscall_provenance.jsonl",
         target="G(open -> F(close))"),
    dict(name="real-network", a="connect", b="close",
         pool="data/poison_pool/real-network_connect_close_pool.txt",
         prov="data/provenance/real-network_provenance.jsonl",
         target="G(connect -> F(close))"),
]
os.makedirs("results", exist_ok=True); os.makedirs("figures", exist_ok=True)

def target_conf(traces, a, b):
    s = n = 0
    for t in traces:
        ant, sat = mb.check_response(t, a, b)
        if ant:
            n += 1; s += int(sat)
    return s, n, (s/n if n else 1.0)

def supporting_sources(traces_ws, fn, a, b, theta):
    by = defaultdict(lambda: [0, 0])
    for ev, src in traces_ws:
        ant, sat = fn(ev, a, b)
        if ant:
            by[src][0] += 1; by[src][1] += int(sat)
    return sum(1 for n, sat in by.values() if n and sat/n >= theta), len(by)

def run_corpus(cfg):
    clean = mb.read_texada(Path(f"data/normalized/{cfg['name']}.txt"))
    prov  = [json.loads(l) for l in open(cfg["prov"])]
    pool  = mb.read_texada(Path(cfg["pool"]))
    assert pool, f"empty pool for {cfg['name']}"
    a, b, N = cfg["a"], cfg["b"], len(clean)
    poisoned = lambda K: clean + [pool[i % len(pool)] for i in range(K)]

    # 1. attack
    S0, A0, C0 = target_conf(clean, a, b)
    arows = []
    for K in range(0, 16):
        s, n, c = target_conf(poisoned(K), a, b)
        arows.append({"K": K, "poison_pct": round(100*K/N, 2), "nsat": s, "nant": n,
                      "confidence": round(c, 5), "deleted": c < THETA})
    with open(f"results/{cfg['name']}_attack.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(arows[0])); w.writeheader(); w.writerows(arows)
    emp_K = min((r["K"] for r in arows if r["deleted"]), default=None)

    # 2. closed-form bound
    Kstar = max(0, math.floor(S0/THETA - A0) + 1)

    # 3. detectability
    base = mb.mine_simulated(clean, THETA); pois = mb.mine_simulated(poisoned(emp_K), THETA)
    deleted = sorted({r["property_instance"] for r in base} - {r["property_instance"] for r in pois})
    mc = lambda spec: statistics.mean(r["confidence"] for r in spec) if spec else 0.0
    rng = random.Random(0); boot = [target_conf([clean[rng.randrange(N)] for _ in range(N)], a, b)[2] for _ in range(500)]
    sd = statistics.pstdev(boot); shift = C0 - target_conf(poisoned(emp_K), a, b)[2]
    detect = {"baseline_props": len(base), "poisoned_props": len(pois),
              "baseline_mean_conf": round(mc(base), 4), "poisoned_mean_conf": round(mc(pois), 4),
              "deleted_properties": deleted, "attack_shift": round(shift, 5),
              "bootstrap_sd": round(sd, 5), "shift_in_sigma": round(shift/sd, 2) if sd else None}
    json.dump(detect, open(f"results/{cfg['name']}_detect.json", "w"), indent=2)

    # 4. provenance-quorum defense
    clean_ws = [(r["events"], r["source_id"]) for r in prov]
    att_ws = clean_ws + [(pool[i % len(pool)], "attacker") for i in range(emp_K)]
    S_clean, nsrc = supporting_sources(clean_ws, mb.check_response, a, b, THETA)
    S_att, _ = supporting_sources(att_ws, mb.check_response, a, b, THETA)
    TFN = {k: v[0] for k, v in mb.TEMPLATES.items()}
    psupport = []
    for r in base:
        fn = TFN.get(r["template"])
        if fn is None: continue
        sup, _ = supporting_sources(clean_ws, fn, r["event_a"], r["event_b"], THETA)
        psupport.append(sup)
    drows = []
    for q in range(1, nsrc + 1):
        fp = sum(1 for sup in psupport if sup < q)
        drows.append({"q": q, "clean_supporting_sources": S_clean, "attacked_supporting_sources": S_att,
                      "target_recovered": (target_conf(poisoned(emp_K), a, b)[2] < THETA) and (S_att >= q),
                      "false_positives": fp, "false_positive_rate": round(fp/len(psupport), 4),
                      "certified_max_compromised_sources": max(0, S_clean - q)})
    with open(f"results/{cfg['name']}_defense.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(drows[0])); w.writeheader(); w.writerows(drows)
    t0 = time.perf_counter(); [target_conf(clean, a, b) for _ in range(50)]; tg = (time.perf_counter()-t0)/50
    t0 = time.perf_counter(); [supporting_sources(clean_ws, mb.check_response, a, b, THETA) for _ in range(50)]; ts = (time.perf_counter()-t0)/50

    return {"corpus": cfg["name"], "n_traces": N, "n_sources": nsrc, "target": cfg["target"],
            "baseline_conf": round(C0, 5), "emp_delete_K": emp_K, "poison_pct": round(100*emp_K/N, 2),
            "Kstar": Kstar, "bound_matches": Kstar == emp_K,
            "deleted_props": detect["deleted_properties"],
            "mean_conf_change": round(detect["poisoned_mean_conf"] - detect["baseline_mean_conf"], 4),
            "shift_in_sigma": detect["shift_in_sigma"],
            "clean_supporting_sources": S_clean, "recovered_for_q_le": max((r["q"] for r in drows if r["target_recovered"]), default=0),
            "fp_rate_at_q2": next((r["false_positive_rate"] for r in drows if r["q"] == 2), None),
            "overhead_factor": round(ts/tg, 2),
            "_attack": arows, "_defense": drows}

results = [run_corpus(c) for c in CFGS]
json.dump([{k: v for k, v in r.items() if not k.startswith("_")} for r in results],
          open("results/summary.json", "w"), indent=2)

# combined figure: one row per corpus (attack | defense)
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
fig, ax = plt.subplots(len(results), 2, figsize=(11, 4*len(results)))
for i, r in enumerate(results):
    ks=[x["K"] for x in r["_attack"]]; cs=[x["confidence"] for x in r["_attack"]]
    ax[i][0].plot(ks, cs, "o-"); ax[i][0].axhline(THETA, ls="--", color="r", label=f"θ={THETA}")
    ax[i][0].axvline(r["emp_delete_K"], ls=":", color="gray", label=f"delete K={r['emp_delete_K']}")
    ax[i][0].set_title(f"{r['corpus']}: {r['target']}"); ax[i][0].set_xlabel("poison K"); ax[i][0].set_ylabel("confidence"); ax[i][0].legend(fontsize=8)
    qs=[x["q"] for x in r["_defense"]]; fps=[x["false_positive_rate"] for x in r["_defense"]]; rec=[1 if x["target_recovered"] else 0 for x in r["_defense"]]
    ax[i][1].plot(qs, fps, "s-", label="false-positive rate"); ax[i][1].plot(qs, rec, "^-", label="recovered (1/0)")
    ax[i][1].set_title(f"{r['corpus']}: provenance-quorum"); ax[i][1].set_xlabel("quorum q"); ax[i][1].legend(fontsize=8)
plt.tight_layout(); plt.savefig("figures/clean_trace_results.png", dpi=130)

for r in results:
    print(f"[{r['corpus']}] N={r['n_traces']} src={r['n_sources']} {r['target']} base={r['baseline_conf']} "
          f"deleteK={r['emp_delete_K']}({r['poison_pct']}%) K*={r['Kstar']} match={r['bound_matches']} "
          f"shift={r['shift_in_sigma']}σ recover<=q{r['recovered_for_q_le']} FP@q2={r['fp_rate_at_q2']} ovh={r['overhead_factor']}x")
