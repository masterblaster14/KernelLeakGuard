// SPDX-License-Identifier: GPL-2.0
/*
 * L04 - partial allocation in a loop.
 * If allocating descriptor i fails, descriptors 0..i-1 are never released.
 */
#include <linux/slab.h>
#include <linux/string.h>
#include "klg_harness.h"

#define NR_DESC   4
#define DESC_SIZE 128

static noinline int ring_alloc(void)
{
	void *desc[NR_DESC];
	int i;

	for (i = 0; i < NR_DESC; i++) {
		desc[i] = kmalloc(DESC_SIZE, GFP_KERNEL);	/* GT:LEAK */
		if (!desc[i])
			return -ENOMEM;	/* earlier descriptors leak */
	}

	for (i = 0; i < NR_DESC; i++)
		memset(desc[i], 0, DESC_SIZE);
	for (i = 0; i < NR_DESC; i++)
		kfree(desc[i]);
	return 0;
}

KLG_TRIGGER(ring_alloc);
KLG_SIMPLE_MODULE("KLG L04: loop allocation without rollback");
