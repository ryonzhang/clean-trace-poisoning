#!/usr/bin/env python3
"""run_stealth_margin.py — Characterize stealth as a function of the target's
confidence margin, to answer: is the 'hides within sigma' result just an artifact
of choosing a marginal target? For every mined response property we compute the
deletion budget K* and the induced confidence shift, and compare it to that
property's own bootstrap resampling sigma. Result: only near-threshold (fragile)
properties delete within sampling variance; robustly-supported safety properties
are deletable but NOT stealthily."""
import sys, json, csv, math, random, statistics, os
from pathlib import Path
sys.path.insert(0,"scripts"); import mine_baseline as mb
THETA=0.9
CFGS=[("real-syscall",),("real-network",)]
os.makedirs("results",exist_ok=True); os.makedirs("figures",exist_ok=True)

import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
fig,ax=plt.subplots(1,2,figsize=(11,4)); rows=[]
for k,(name,) in enumerate(CFGS):
    traces=mb.read_texada(Path(f"data/normalized/{name}.txt")); N=len(traces)
    spec=[r for r in mb.mine_simulated(traces,THETA) if r["template"]=="RESPONSE"]
    rng=random.Random(0); B=400
    xs=[]; ys=[]; det=[]
    for r in spec:
        a,b=r["event_a"],r["event_b"]; S,A,c=r["nsat"],r["nant"],r["confidence"]
        Kstar=max(0,math.floor(S/THETA-A)+1)
        shift=c - S/(A+Kstar)
        # bootstrap sigma of this property's confidence over resamples of the corpus
        confs=[]
        for _ in range(B):
            s=n=0
            for _ in range(N):
                t=traces[rng.randrange(N)]; ant,sat=mb.check_response(t,a,b)
                if ant: n+=1; s+=int(sat)
            confs.append(s/n if n else 1.0)
        sigma=statistics.pstdev(confs)
        stealth = shift/sigma if sigma>1e-9 else float('inf')
        rows.append(dict(corpus=name,property=r["property_instance"],margin=round(c-THETA,4),
                         Kstar=Kstar,poison_pct=round(100*Kstar/N,2),conf_shift=round(shift,4),
                         sigma=round(sigma,4),stealth_in_sigma=(round(stealth,2) if sigma>1e-9 else None)))
        if sigma>1e-9:
            xs.append(c-THETA); ys.append(stealth); det.append(stealth>1)
    if xs:
        ax[k].scatter([x for x,d in zip(xs,det) if not d],[y for y,d in zip(ys,det) if not d],c="green",label="within 1σ (stealthy)",zorder=4)
        ax[k].scatter([x for x,d in zip(xs,det) if d],[y for y,d in zip(ys,det) if d],c="red",marker="^",label=">1σ (detectable)",zorder=4)
        ax[k].axhline(1.0,ls="--",color="gray",label="1σ stealth boundary")
    ax[k].set_xlabel("target confidence margin (c-θ)"); ax[k].set_ylabel("deletion shift / σ")
    ax[k].set_title(f"{name}: stealth vs. margin"); ax[k].legend(fontsize=8)
plt.tight_layout(); plt.savefig("figures/stealth_margin.png",dpi=130)
with open("results/stealth_margin.csv","w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

# summary
for name in [c[0] for c in CFGS]:
    rs=[r for r in rows if r["corpus"]==name]
    fin=[r for r in rs if r["stealth_in_sigma"] is not None]
    stealthy=[r for r in fin if r["stealth_in_sigma"]<=1]
    perfect=[r for r in rs if r["stealth_in_sigma"] is None]
    print(f"{name}: {len(rs)} response props | {len(stealthy)} delete within 1σ (stealthy), "
          f"{len(fin)-len(stealthy)} detectable (>1σ), {len(perfect)} perfectly-supported (σ=0, always detectable)")
    for r in sorted(fin,key=lambda r:r['margin'])[:6]:
        print(f"   margin={r['margin']:.3f} K*={r['Kstar']:2d} ({r['poison_pct']:.1f}%) shift={r['conf_shift']:.3f} σ={r['sigma']:.3f} -> {r['stealth_in_sigma']}σ")
print("wrote results/stealth_margin.csv, figures/stealth_margin.png")
