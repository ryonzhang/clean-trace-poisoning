#!/usr/bin/env python3
"""run_extended.py — additional experiments to strengthen the evaluation:
   (A) multi-source attacker validating Theorem 2 (c>1),
   (B) budget landscape across all mined response properties,
   (C) threshold sensitivity sweep.
Outputs results/*.csv and figures/clean_trace_extended.png."""
import sys, json, csv, math, os
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, "scripts"); import mine_baseline as mb

THETA = 0.9
CFGS = [dict(name="real-syscall", a="open", b="close", prov="data/provenance/real-syscall_provenance.jsonl"),
        dict(name="real-network", a="connect", b="close", prov="data/provenance/real-network_provenance.jsonl")]
os.makedirs("results", exist_ok=True)

def conf(traces, fn, a, b):
    s=n=0
    for t in traces:
        ant,sat=fn(t,a,b)
        if ant: n+=1; s+=int(sat)
    return s,n

def per_source(prov, fn, a, b):
    by=defaultdict(lambda:[0,0])
    for r in prov:
        ant,sat=fn(r["events"],a,b)
        if ant: by[r["source_id"]][0]+=1; by[r["source_id"]][1]+=int(sat)
    return by

land_rows=[]; ms_rows=[]; thr_rows=[]
for cfg in CFGS:
    clean=mb.read_texada(Path(f"data/normalized/{cfg['name']}.txt"))
    prov=[json.loads(l) for l in open(cfg["prov"])]
    a,b=cfg["a"],cfg["b"]

    # (A) multi-source attacker: c compromised sources flip from supporting->non.
    by=per_source(prov, mb.check_response, a, b)
    supporting=[s for s,(n,sat) in by.items() if n and sat/n>=THETA]
    Sclean=len(supporting); nsrc=len(by)
    for q in range(1, nsrc+1):
        for c in range(0, Sclean+1):
            # worst case: c supporting sources become non-supporting
            remaining = Sclean - c
            recovered = remaining >= q
            cert = (c <= Sclean - q)
            ms_rows.append({"corpus":cfg['name'],"q":q,"c_compromised":c,
                            "supporting_after":remaining,"recovered":recovered,
                            "within_cert_bound":cert,"bound_holds":recovered==cert})

    # (B) budget landscape across all RESPONSE properties
    spec=mb.mine_simulated(clean, THETA)
    for r in spec:
        if r["template"]!="RESPONSE": continue
        S,A=r["nsat"],r["nant"]
        K=max(0, math.floor(S/THETA - A)+1)
        land_rows.append({"corpus":cfg['name'],"property":r["property_instance"],
                          "antecedent_freq":r["antecedent_frequency"],"confidence":r["confidence"],
                          "Kstar":K,"poison_pct":round(100*K/len(clean),2)})

    # (C) threshold sensitivity
    for th in [0.80,0.85,0.90,0.95]:
        spec_t=mb.mine_simulated(clean, th)
        resp=[r for r in spec_t if r["template"]=="RESPONSE"]
        tconf=None; tK=None
        for r in resp:
            if r["event_a"]==a and r["event_b"]==b:
                tconf=r["confidence"]; tK=max(0,math.floor(r["nsat"]/th - r["nant"])+1)
        thr_rows.append({"corpus":cfg['name'],"theta":th,"n_props":len(spec_t),
                         "n_response":len(resp),"target_conf":tconf,"target_Kstar":tK})

for fn,rows in [("multisource",ms_rows),("budget_landscape",land_rows),("threshold_sweep",thr_rows)]:
    with open(f"results/{fn}.csv","w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

# summaries
print("=== (A) multi-source: Theorem 2 bound check ===")
for cfg in CFGS:
    rs=[r for r in ms_rows if r["corpus"]==cfg["name"]]
    print(f"  {cfg['name']}: bound holds for {sum(r['bound_holds'] for r in rs)}/{len(rs)} (c,q) cells")
print("=== (B) budget landscape ===")
for cfg in CFGS:
    rs=[r for r in land_rows if r["corpus"]==cfg["name"]]
    ks=sorted(r["Kstar"] for r in rs)
    cheap=sum(1 for k in ks if k<=5)
    print(f"  {cfg['name']}: {len(rs)} response props, median K*={ks[len(ks)//2]}, deletable with <=5 traces: {cheap}/{len(rs)}")
print("=== (C) threshold sweep (target K*) ===")
for cfg in CFGS:
    rs=[r for r in thr_rows if r["corpus"]==cfg["name"]]
    print(f"  {cfg['name']}: "+", ".join(f"θ{r['theta']}:K*={r['target_Kstar']}(props {r['n_props']})" for r in rs))

# figure: budget-landscape scatter (K* vs antecedent_freq) + multisource recovery line
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
fig,ax=plt.subplots(1,2,figsize=(11,4))
for cfg,mk in zip(CFGS,["o","s"]):
    rs=[r for r in land_rows if r["corpus"]==cfg["name"]]
    ax[0].scatter([r["antecedent_freq"] for r in rs],[r["Kstar"] for r in rs],marker=mk,label=cfg["name"],alpha=.7)
ax[0].set_xlabel("antecedent frequency"); ax[0].set_ylabel("deletion budget K*"); ax[0].set_title("Budget landscape (response properties)"); ax[0].legend(fontsize=8)
for cfg,mk in zip(CFGS,["o","s"]):
    rs=[r for r in ms_rows if r["corpus"]==cfg["name"] and r["q"]==2]
    ax[1].plot([r["c_compromised"] for r in rs],[1 if r["recovered"] else 0 for r in rs],mk+"-",label=f"{cfg['name']} (q=2)")
ax[1].set_xlabel("compromised sources c"); ax[1].set_ylabel("target recovered (1/0)"); ax[1].set_title("Multi-source attacker (Thm 2)"); ax[1].legend(fontsize=8)
plt.tight_layout(); plt.savefig("figures/clean_trace_extended.png",dpi=130)
print("wrote results/multisource.csv, budget_landscape.csv, threshold_sweep.csv, figures/clean_trace_extended.png")
