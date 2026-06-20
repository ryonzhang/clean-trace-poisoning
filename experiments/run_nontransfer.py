#!/usr/bin/env python3
"""run_nontransfer.py — Empirically show per-sample outlier defenses do NOT
catch clean-trace poison. Fit IsolationForest and LOF on the CLEAN corpus
(bag-of-events feature vectors) and score the legal poison traces. If poison is
indistinguishable, its anomaly scores fall within the clean distribution and the
threshold that flags all poison also flags many legitimate traces."""
import sys, json, csv, os
import numpy as np
from pathlib import Path
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
sys.path.insert(0,"scripts"); import mine_baseline as mb

os.makedirs("results", exist_ok=True); os.makedirs("figures", exist_ok=True)
CFGS=[dict(name="real-syscall",pool="data/poison_pool/real-syscall_open_close_pool.txt"),
      dict(name="real-network",pool="data/poison_pool/real-network_connect_close_pool.txt")]

def featurize(traces, vocab):
    X=np.zeros((len(traces),len(vocab)))
    for i,t in enumerate(traces):
        for e in t:
            if e in vocab: X[i,vocab[e]]+=1
    return X

rows=[]; import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
fig,ax=plt.subplots(1,2,figsize=(11,4))
for k,cfg in enumerate(CFGS):
    clean=mb.read_texada(Path(f"data/normalized/{cfg['name']}.txt"))
    pool=mb.read_texada(Path(cfg["pool"]))
    vocab={e:i for i,e in enumerate(sorted({x for t in clean for x in t}))}
    Xc=featurize(clean,vocab); Xp=featurize(pool,vocab)
    # IsolationForest: higher score_samples = more normal; use -score as anomaly
    iso=IsolationForest(random_state=0,contamination='auto').fit(Xc)
    sc_clean=-iso.score_samples(Xc); sc_pois=-iso.score_samples(Xp)
    # LOF (novelty) for a second detector
    lof=LocalOutlierFactor(n_neighbors=min(20,len(clean)-1),novelty=True).fit(Xc)
    lc=-lof.score_samples(Xc); lp=-lof.score_samples(Xp)
    # If we set the threshold to flag ALL poison, what fraction of clean is also flagged?
    thr=sc_pois.min()                      # catch every poison trace
    fp_clean=float(np.mean(sc_clean>=thr)) # legitimate traces wrongly flagged
    # are poison scores within clean range?
    within=float(np.mean((sc_pois>=sc_clean.min())&(sc_pois<=np.percentile(sc_clean,95))))
    rows.append(dict(corpus=cfg['name'],detector="IsolationForest",
                     poison_mean=round(float(sc_pois.mean()),4),clean_mean=round(float(sc_clean.mean()),4),
                     clean_p95=round(float(np.percentile(sc_clean,95)),4),
                     fp_to_catch_all_poison=round(fp_clean,3),
                     poison_within_clean_central=round(within,3)))
    thr2=lp.min(); fp2=float(np.mean(lc>=thr2))
    rows.append(dict(corpus=cfg['name'],detector="LOF",
                     poison_mean=round(float(lp.mean()),4),clean_mean=round(float(lc.mean()),4),
                     clean_p95=round(float(np.percentile(lc,95)),4),
                     fp_to_catch_all_poison=round(fp2,3),
                     poison_within_clean_central=round(float(np.mean((lp>=lc.min())&(lp<=np.percentile(lc,95)))),3)))
    # plot IsolationForest score distributions (counts), with poison overlaid at a visible height
    counts,_,_=ax[k].hist(sc_clean,bins=20,alpha=.55,label="clean traces",color="#4C72B0")
    ymax=max(counts) if len(counts) else 1
    yp=0.55*ymax
    # stems from axis to each poison marker, then the marker, so position is unambiguous
    ax[k].vlines(sc_pois,0,yp,color="red",lw=1,alpha=.6)
    ax[k].scatter(sc_pois,np.full(len(sc_pois),yp),color="red",marker="X",s=90,
                  edgecolor="black",linewidth=0.6,label=f"poison traces (n={len(sc_pois)})",zorder=6)
    ax[k].axvline(np.percentile(sc_clean,95),ls="--",color="gray",label="clean 95th pct")
    ax[k].set_ylim(0,ymax*1.15)
    ax[k].set_title(f"{cfg['name']}: IsolationForest anomaly score")
    ax[k].set_xlabel("anomaly score"); ax[k].set_ylabel("number of traces"); ax[k].legend(fontsize=8,loc="upper left")
plt.tight_layout(); plt.savefig("figures/nontransfer.png",dpi=130)
with open("results/nontransfer.csv","w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
for r in rows: print(r)
print("wrote results/nontransfer.csv, figures/nontransfer.png")
