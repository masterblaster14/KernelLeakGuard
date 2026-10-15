savedcmd_brd.ko := ld.lld -r -m elf_x86_64 --fatal-warnings -z noexecstack --build-id=sha1  -T /home/gupta/klg-build/kbuild/scripts/module.lds -o brd.ko brd.o brd.mod.o .module-common.o
