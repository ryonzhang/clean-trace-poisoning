#!/usr/bin/env python3
"""gen_real_network.py — REAL network/socket trace corpus via strace.

A loopback HTTP/echo server (untraced infrastructure) accepts connections; a set
of DISTINCT real client programs connect to it and are each traced separately.
Each client process becomes one trace over the socket-lifecycle alphabet
{socket,bind,listen,accept,connect,send,recv,shutdown,sockopt,close}. Nothing is
synthesized. A native C leak client connect()s and _exit()s WITHOUT close(),
giving genuine connect-without-close counterexamples to G(connect -> F(close)).

NATIVE PROVENANCE: source_id = client program (curl/wget/nc/ssh/python/c/leak).
"""
import argparse, os, re, socket, subprocess, tempfile, threading, random, glob, json, time
from collections import Counter

NETMAP = {"socket":"socket","socketpair":"socket","bind":"bind","listen":"listen",
"accept":"accept","accept4":"accept","connect":"connect","sendto":"send","send":"send",
"sendmsg":"send","sendmmsg":"send","recvfrom":"recv","recv":"recv","recvmsg":"recv",
"recvmmsg":"recv","shutdown":"shutdown","setsockopt":"sockopt","getsockopt":"sockopt",
"close":"close"}
SYS = re.compile(r'^([a-z_][a-z0-9_]*)\(')

C_CLIENT = r'''
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <string.h>
#include <stdlib.h>
int main(int argc,char**argv){
  int leak = argc>2 && argv[2][0]=='1';
  int s=socket(AF_INET,SOCK_STREAM,0);
  struct sockaddr_in a; memset(&a,0,sizeof a); a.sin_family=AF_INET;
  a.sin_port=htons(atoi(argv[1])); inet_pton(AF_INET,"127.0.0.1",&a.sin_addr);
  if(connect(s,(struct sockaddr*)&a,sizeof a)==0){ send(s,"GET / HTTP/1.0\r\n\r\n",18,0); char b[64]; recv(s,b,64,0); }
  if(!leak) close(s);        /* leak: skip close, _exit reclaims */
  _exit(0);
}
'''

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="data/normalized/real-network.txt")
    ap.add_argument("--rawdir", default="data/raw/real-network")
    ap.add_argument("--provenance", default="data/provenance/real-network_provenance.jsonl")
    ap.add_argument("--n-native-leak", type=int, default=5)
    ap.add_argument("--reps", type=int, default=8)
    args = ap.parse_args()
    random.seed(args.seed)

    # untraced loopback server
    srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0)); srv.listen(64); PORT = srv.getsockname()[1]
    stop = False
    def serve():
        srv.settimeout(0.5)
        while not stop:
            try: c,_ = srv.accept()
            except socket.timeout: continue
            except OSError: break
            try:
                c.settimeout(0.5); 
                try: c.recv(256)
                except Exception: pass
                c.sendall(b"HTTP/1.0 200 OK\r\nContent-Length:2\r\n\r\nok"); c.close()
            except Exception:
                try: c.close()
                except Exception: pass
    th = threading.Thread(target=serve, daemon=True); th.start()

    work = tempfile.mkdtemp(prefix="rn_"); stdir = os.path.join(work,"st"); os.makedirs(stdir)
    runs = []
    def run(argv, source, timeout=6):
        pref = os.path.join(stdir, f"r{random.randint(0,10**9)}")
        try:
            subprocess.run(["strace","-ff","-qq","-e","trace=network,close","-o",pref]+argv,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout)
        except Exception:
            pass
        runs.append((os.path.basename(pref), source))
    def parse(p):
        ev=[]
        try:
            for line in open(p, errors="ignore"):
                line=line.strip()
                if line.startswith(("---","+++")): continue
                m=SYS.match(line)
                if m and m.group(1) in NETMAP: ev.append(NETMAP[m.group(1)])
        except FileNotFoundError: pass
        return ev

    U = f"http://127.0.0.1:{PORT}/"
    # python client (clean): socket/connect/send/recv/close
    pyc = os.path.join(work,"pyc.py")
    open(pyc,"w").write("import socket,sys\n"
        "s=socket.socket();s.connect(('127.0.0.1',%d))\n" % PORT +
        "s.sendall(b'GET / HTTP/1.0\\r\\n\\r\\n');s.recv(64)\n"
        "import sys\n"
        "(s.shutdown(socket.SHUT_RDWR) if len(sys.argv)>1 else None)\n"
        "s.close()\n")
    # C clients (clean + leak)
    csrc=os.path.join(work,"c.c"); cbin=os.path.join(work,"cclient")
    open(csrc,"w").write(C_CLIENT)
    have_c = subprocess.run(["gcc","-O0","-o",cbin,csrc]).returncode==0

    REPS=args.reps
    for _ in range(REPS): run(["curl","-s","-o","/dev/null",U], "curl")
    for _ in range(REPS): run(["wget","-q","-O","/dev/null",U], "wget")
    for _ in range(REPS): run(["bash","-c",f"echo hi | nc -w1 127.0.0.1 {PORT}"], "nc")
    for _ in range(REPS): run(["python3",pyc], "python")
    for _ in range(REPS): run(["python3",pyc,"shutdown"], "python_shutdown")
    for _ in range(REPS): run(["ssh","-o","ConnectTimeout=2","-o","StrictHostKeyChecking=no","-o","BatchMode=yes","-p",str(PORT),"127.0.0.1","true"], "ssh")
    if have_c:
        for _ in range(REPS): run([cbin,str(PORT),"0"], "c_client")
        for _ in range(args.n_native_leak): run([cbin,str(PORT),"1"], "leak_client")

    stop=True; 
    try: srv.close()
    except Exception: pass
    time.sleep(0.3)

    records=[]
    for pref,source in runs:
        for stf in sorted(glob.glob(os.path.join(stdir, pref+"*"))):
            ev=parse(stf)
            if "connect" in ev or "socket" in ev:   # keep real socket-using traces
                if len(ev)>=2: records.append((ev,source))
    random.Random(args.seed).shuffle(records)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    open(args.out,"w").write("".join("\n".join(ev)+"\n\n" for ev,_ in records))
    os.makedirs(os.path.dirname(args.provenance), exist_ok=True)
    with open(args.provenance,"w") as pf:
        for tid,(ev,source) in enumerate(records):
            pf.write(json.dumps({"trace_id":tid,"source_id":source,"events":ev,"compromised":False})+"\n")
    os.makedirs(args.rawdir, exist_ok=True)
    for stf in sorted(glob.glob(os.path.join(stdir,"*")))[:6]:
        try: __import__("shutil").copy(stf, os.path.join(args.rawdir, os.path.basename(stf)+".strace.txt"))
        except Exception: pass

    lens=[len(ev) for ev,_ in records]; alpha=Counter(e for ev,_ in records for e in ev); srcs=Counter(s for _,s in records)
    print(f"traces={len(records)} events={sum(lens)} have_c={have_c} port={PORT}")
    print("alphabet=", dict(alpha)); print("sources=", dict(srcs))
    if lens: print(f"len min/mean/max = {min(lens)}/{round(sum(lens)/len(lens),1)}/{max(lens)}")

if __name__ == "__main__":
    main()
