# KernelLeakGuard

**Detecting and Verifying Linux Kernel Memory Leaks.**

BITE303P Operating Systems Lab project, VIT Vellore, Fall 2026-27:
Om Gunjan Gupta (24BIT0316), Abhishek Kumar Singh (24BIT0309), Aarav Jain (24BIT0023).
Guide: Dr. Arivuselvan K.

Kernel routines often bail out early when something fails (`return -ENOMEM;`,
`goto err;`). If such an exit forgets to release memory allocated earlier, the
kernel leaks memory, but only when the failure actually happens, which normal
testing almost never triggers. KernelLeakGuard

1. **finds** suspicious early exits with an LLVM-based static analyser
   (inspired by MLEE, USENIX ATC 2021),
2. **reproduces** them by failing exactly the right call inside a QEMU/KVM
   virtual machine using the kernel's fault-injection framework (`fail-nth`),
3. **verifies** them with the kernel memory leak detector (kmemleak) and labels
   each warning **confirmed**, **not reproduced** or **inconclusive**, with the
   evidence attached.

```
 kernel module C ──► clang -emit-llvm ──► klg-analyze (C++/LLVM) ──► candidates.json
                                                                        │
          ┌─────────────────────────────────────────────────────────────┘
          ▼
 QEMU/KVM guest (Linux 6.18.55 + kmemleak + fault injection)
   klg-agent sweep   : fail-nth = 1,2,3...  → map fault point → source line
   klg-agent repeat  : fail the candidate's trigger call ×3
   kmemleak scan     : unreferenced objects + allocation backtraces
          │
          ▼
 klg verify (Python) : faddr2line symbolisation, attribution, verdicts
 klg evaluate        : precision / recall vs ground truth, baselines
 dashboard (Streamlit)
```

## Repository layout

| Path | Contents | Owner |
|---|---|---|
| `analyzer/` | `klg-analyze`, the static analyser (C++17, LLVM 21) | Om Gunjan Gupta |
| `vm/` | guest kernel config, kernel/initramfs build, QEMU launcher, guest init | Abhishek Kumar Singh |
| `runtime/` | `klg-agent`, the in-guest fault-injection driver (C) | Abhishek Kumar Singh |
| `corpus/` | 32 benchmark kernel modules with ground-truth annotations | Aarav Jain |
| `klg/` | Python orchestrator: build, analyse, verify, evaluate | Aarav Jain |
| `dashboard/` | Streamlit dashboard | Aarav Jain |
| `docs/` | report, user manual, presentation | all |
| `results/` | analysis output, runtime evidence, evaluation | generated |

## Requirements

* Windows 11 with WSL2 (Ubuntu 24.04+) or native Linux x86-64, with KVM (`/dev/kvm`)
* ~25 GB disk, 8 GB RAM
* Packages:
  ```bash
  sudo apt install -y build-essential clang llvm llvm-dev lld libclang-dev \
    qemu-system-x86 flex bison bc libelf-dev libssl-dev dwarves cpio busybox-static \
    python3-venv python3-pip git curl xz-utils rsync kmod
  sudo usermod -aG kvm $USER     # then restart WSL / log in again
  ```

## Quick start

```bash
cd ~/KernelLeakGuard
./vm/build_kernel.sh            # download + build Linux 6.18.55 (~10 min first time)
./vm/build_initramfs.sh         # busybox guest + klg-agent
make -C analyzer                # build klg-analyze
./scripts/setup_venv.sh         # Python environment for dashboard/reports

python3 -m klg all              # build corpus → analyse → verify in VM → evaluate
.venv/bin/streamlit run dashboard/app.py   # open http://localhost:8501

bash scripts/demo_ready.sh --open           # before a demo: check everything, open dashboard/slides
python3 scripts/live_demo.py --window       # live demo on the VM's own screen (opens in the browser)
python3 scripts/live_demo.py shell --window # root shell inside the VM
```

Real-kernel experiments (`python3 -m klg real`, `klg seed`) also need the
39 modules of `vm/real_modules.fragment`, which `build_kernel.sh` builds.
`GUIDE.md` (and `docs/KernelLeakGuard_Study_Guide.pdf`) explains the whole project in
plain language with diagrams, a code tour and a glossary; `DEMO.md` (and
`docs/KernelLeakGuard_Demo_Guide.pdf`) is the step-by-step demo script; `HANDOFF.md`
describes the whole project state in detail.

Individual steps: `python3 -m klg build | analyze [--all-variants] | verify | evaluate | show`.

Further commands:
```bash
python3 -m klg fix                       # fix patches for confirmed leaks, validated
                                         # (compile, re-analysis, VM re-run) → results/fixes/
python3 -m klg real [--only a,b,c]       # real Linux modules (vm/real_modules.fragment):
                                         # static analysis + VM verification → results/real/
python3 -m klg seed [--only name]        # reintroduce a known leak into a real module and
                                         # detect → confirm → fix it → results/seeded/
bash scripts/build_docs.sh               # tests, figures, report, slides, manual
```

Analyse any LLVM bitcode directly:
```bash
analyzer/build/klg-analyze module.bc -o findings.json [--naive|--no-escape|--no-interproc|--no-corr|--no-containers]
```

See `docs/User_Manual.docx` for a complete walkthrough.

## Third-party code

`dashboard/novnc/` is the noVNC 1.5.0 viewer (https://github.com/novnc/noVNC,
MPL-2.0, see its `LICENSE.txt`), used unmodified to show the VM screen in the browser.
