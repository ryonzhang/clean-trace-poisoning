#!/usr/bin/env python3
"""gen_real_syscall.py — Build a REAL syscall-trace corpus with strace.

Each traced process execution becomes one trace of file-descriptor lifecycle
events. Nothing is synthesized. Well-behaved tools close descriptors; a native
leak program open()s and _exit()s WITHOUT close(), giving genuine
open-without-close counterexamples to G(open -> F(close)).

NATIVE PROVENANCE: every trace is tagged with the program that produced it
(cat/grep/python/leak/...), written to data/provenance/real-syscall_provenance.jsonl.
"""
import argparse, os, re, subprocess, tempfile, random, glob, shutil, json
from collections import Counter

MAP = {"openat":"open","open":"open","creat":"open","read":"read","pread64":"read",
"readv":"read","write":"write","pwrite64":"write","writev":"write","lseek":"lseek",
"close":"close","fstat":"stat","newfstatat":"stat","statx":"stat","stat":"stat",
"lstat":"stat","dup":"dup","dup2":"dup","dup3":"dup","mmap":"mmap","mmap2":"mmap"}
SYS = re.compile(r'^([a-z_][a-z0-9_]*)\(')

LEAK_C = r'''
#include <fcntl.h>
#include <unistd.h>
#include <stdlib.h>
int main(int argc,char**argv){
  int n = argc>1?atoi(argv[1]):3;
  for(int i=0;i<n;i++){ int fd=open(argv[2],O_RDONLY); char b[64]; read(fd,b,64); }
  _exit(0);
}
'''

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="data/normalized/real-syscall.txt")
    ap.add_argument("--rawdir", default="data/raw/real-syscall")
    ap.add_argument("--provenance", default="data/provenance/real-syscall_provenance.jsonl")
    ap.add_argument("--leak-frac", type=float, default=0.0)
    ap.add_argument("--n-native-leak", type=int, default=8)
    args = ap.parse_args()
    random.seed(args.seed)

    work = tempfile.mkdtemp(prefix="rt_"); stdir = os.path.join(work,"st"); os.makedirs(stdir)
    runs = []

    def run(argv, source, timeout=5):
        pref = os.path.join(stdir, f"r{random.randint(0,10**9)}")
        try:
            subprocess.run(["strace","-ff","-qq","-e","trace=%desc,%file","-o",pref]+argv,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout)
        except Exception:
            pass
        runs.append((os.path.basename(pref), source))

    def parse(p):
        ev = []
        try:
            for line in open(p, errors="ignore"):
                line = line.strip()
                if line.startswith(("---","+++")): continue
                m = SYS.match(line)
                if m and m.group(1) in MAP: ev.append(MAP[m.group(1)])
        except FileNotFoundError:
            pass
        return ev

    inputs = []
    for i in range(6):
        p = os.path.join(work, f"in{i}.txt")
        open(p,"w").write("\n".join(f"l{j} w{j%7}" for j in range(random.randint(15,80))))
        inputs.append(p)
    sysfiles = [f for f in ["/etc/hostname","/etc/hosts","/etc/passwd","/etc/protocols"] if os.path.exists(f)]
    allf = inputs + sysfiles

    leak_src = os.path.join(work,"leak.c"); leak_bin = os.path.join(work,"leak")
    open(leak_src,"w").write(LEAK_C)
    have_leak = subprocess.run(["gcc","-O0","-o",leak_bin,leak_src]).returncode == 0

    CMDS = [(["cat","{f}"],"cat"),(["head","-n3","{f}"],"head"),(["tail","-n3","{f}"],"tail"),
            (["wc","{f}"],"wc"),(["grep","w3","{f}"],"grep"),(["cut","-c1-4","{f}"],"cut"),
            (["sha256sum","{f}"],"sha256sum"),(["nl","{f}"],"nl"),(["rev","{f}"],"rev"),
            (["uniq","{f}"],"uniq")]
    for cmd, src in CMDS:
        for f in random.sample(allf, k=5):
            run([c.replace("{f}", f) for c in cmd], src)
    for i in range(40):
        s = os.path.join(work, f"p{i}.py"); f = random.choice(allf)
        if random.random() < args.leak_frac:
            open(s,"w").write(f"fh=open({f!r});fh.read()\n")
        else:
            open(s,"w").write(f"fh=open({f!r});fh.read();fh.close()\n")
        run(["python3", s], "python")
    if have_leak:
        for _ in range(args.n_native_leak):
            run([leak_bin, str(random.randint(1,4)), random.choice(allf)], "leak")

    records = []
    for pref, source in runs:
        for stf in sorted(glob.glob(os.path.join(stdir, pref + "*"))):
            ev = parse(stf)
            if len(ev) >= 3:
                records.append((ev, source))
    random.Random(args.seed).shuffle(records)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    open(args.out,"w").write("".join("\n".join(ev)+"\n\n" for ev,_ in records))
    os.makedirs(os.path.dirname(args.provenance), exist_ok=True)
    with open(args.provenance,"w") as pf:
        for tid,(ev,source) in enumerate(records):
            pf.write(json.dumps({"trace_id":tid,"source_id":source,"events":ev,"compromised":False})+"\n")
    os.makedirs(args.rawdir, exist_ok=True)
    for stf in sorted(glob.glob(os.path.join(stdir,"*")))[:6]:
        shutil.copy(stf, os.path.join(args.rawdir, os.path.basename(stf)+".strace.txt"))

    lens=[len(ev) for ev,_ in records]; alpha=Counter(e for ev,_ in records for e in ev); srcs=Counter(s for _,s in records)
    print(f"traces={len(records)} events={sum(lens)} leak_bin={have_leak}")
    print("alphabet=", dict(alpha)); print("sources=", dict(srcs))
    print(f"len min/mean/max = {min(lens)}/{round(sum(lens)/len(lens),1)}/{max(lens)}")

if __name__ == "__main__":
    main()
