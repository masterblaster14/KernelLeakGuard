# Statically linked so it runs inside the busybox-only guest initramfs.
CC ?= gcc
CFLAGS ?= -O2 -Wall -Wextra -Wno-unused-result

klg-agent: klg-agent.c
	$(CC) $(CFLAGS) -static -o $@ $<

clean:
	rm -f klg-agent

.PHONY: clean
