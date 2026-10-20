#!/bin/bash
# Analyser regression: corpus (all variants) + real-module warning diff vs cached results.
cd /home/gupta/KernelLeakGuard
make -C analyzer 2>&1 | grep -E "error|warning:"
for v in full naive no-escape no-interproc no-containers no-corr; do python3 scripts/try_static.py $v 2>&1 | grep "TP="; done
S=${1:-/tmp/klg_regress}; mkdir -p $S
for bc in results/real/ir/*.bc; do m=$(basename $bc .bc); analyzer/build/klg-analyze $bc -o $S/$m.json --module-name $m >/dev/null 2>&1; done
python3 - "$S" <<'PY'
import json,glob,os,sys
S=sys.argv[1]; n=o=0
for f in sorted(glob.glob(S+'/*.json')):
    m=os.path.basename(f)[:-5]
    a={(c['function'],c['alloc']['line'],c['exit']['line']):c for c in json.load(open(f))['candidates']}
    b={(c['function'],c['alloc']['line'],c['exit']['line']):c for c in json.load(open(f'results/real/static/full/{m}.json'))['candidates']}
    n+=len(a); o+=len(b)
    for k in sorted(set(a)-set(b)): print('+',m,k,a[k]['allocator'])
    for k in sorted(set(b)-set(a)): print('-',m,k,b[k]['allocator'])
print('real warnings: cached',o,'now',n)
PY
