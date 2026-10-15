// SPDX-License-Identifier: GPL-2.0
/*
 * S09 - loop allocation with a correct rollback loop (fixed L04).
 * Proving this safe requires reasoning about the loop counter, which a
 * path-based static analysis cannot do; runtime verification resolves it.
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
		desc[i] = kmalloc(DESC_SIZE, GFP_KERNEL);	/* GT:SAFE */
		if (!desc[i])
			goto rollback;
	}

	for (i = 0; i < NR_DESC; i++)
		memset(desc[i], 0, DESC_SIZE);
	for (i = 0; i < NR_DESC; i++)
		kfree(desc[i]);
	return 0;

rollback:
	while (--i >= 0)
		kfree(desc[i]);
	return -ENOMEM;
}

KLG_TRIGGER(ring_alloc);
KLG_SIMPLE_MODULE("KLG S09: loop allocation with rollback");
