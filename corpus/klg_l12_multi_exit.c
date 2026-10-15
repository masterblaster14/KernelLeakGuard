// SPDX-License-Identifier: GPL-2.0
/*
 * L12 - several error exits, only one of them is wrong.
 * The CRC buffer failure path frees the header but forgets the packet.
 */
#include <linux/slab.h>
#include <linux/string.h>
#include "klg_harness.h"

static noinline int packet_prepare(void)
{
	u8 *pkt, *hdr, *crc, *meta;

	pkt = kmalloc(1500, GFP_KERNEL);	/* GT:LEAK */
	if (!pkt)
		return -ENOMEM;

	hdr = kmalloc(64, GFP_KERNEL);		/* GT:SAFE */
	if (!hdr) {
		kfree(pkt);
		return -ENOMEM;
	}

	crc = kmalloc(32, GFP_KERNEL);		/* GT:SAFE */
	if (!crc) {
		kfree(hdr);
		return -ENOMEM;		/* BUG: pkt is not freed */
	}

	meta = kmalloc(16, GFP_KERNEL);		/* GT:SAFE */
	if (!meta) {
		kfree(crc);
		kfree(hdr);
		kfree(pkt);
		return -ENOMEM;
	}

	memset(pkt, 0, 1500);
	memset(hdr, 0, 64);
	memset(crc, 0, 32);
	memset(meta, 0, 16);
	kfree(meta);
	kfree(crc);
	kfree(hdr);
	kfree(pkt);
	return 0;
}

KLG_TRIGGER(packet_prepare);
KLG_SIMPLE_MODULE("KLG L12: one of several error exits leaks");
