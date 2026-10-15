// SPDX-License-Identifier: GPL-2.0
/*
 * S12 - allocator families paired with their matching release functions:
 * kvmalloc/kvfree, vzalloc/vfree and kmalloc/kfree_sensitive.
 */
#include <linux/mm.h>
#include <linux/slab.h>
#include <linux/string.h>
#include <linux/vmalloc.h>
#include "klg_harness.h"

static noinline int keyring_load(void)
{
	u8 *table, *bitmap;
	char *secret;

	table = kvmalloc(32 * 1024, GFP_KERNEL);	/* GT:SAFE */
	if (!table)
		return -ENOMEM;

	bitmap = vzalloc(8 * 1024);			/* GT:SAFE */
	if (!bitmap) {
		kvfree(table);
		return -ENOMEM;
	}

	secret = kmalloc(64, GFP_KERNEL);		/* GT:SAFE */
	if (!secret) {
		vfree(bitmap);
		kvfree(table);
		return -ENOMEM;
	}

	memset(secret, 0x5a, 64);
	memset(table, 0, 32 * 1024);
	kfree_sensitive(secret);
	vfree(bitmap);
	kvfree(table);
	return 0;
}

KLG_TRIGGER(keyring_load);
KLG_SIMPLE_MODULE("KLG S12: kvmalloc/vzalloc/kfree_sensitive pairs");
