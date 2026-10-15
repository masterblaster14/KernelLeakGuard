# Shared paths for KernelLeakGuard scripts. Source this file; do not execute.
KVER="${KVER:-6.18.55}"
KLG_WORK="${KLG_WORK:-$HOME/klg-build}"
KSRC="${KSRC:-$KLG_WORK/linux-$KVER}"
KBUILD="${KBUILD:-$KLG_WORK/kbuild}"
BZIMAGE="$KBUILD/arch/x86/boot/bzImage"
INITRAMFS="$KLG_WORK/initramfs.cpio.gz"
