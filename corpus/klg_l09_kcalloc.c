// SPDX-License-Identifier: GPL-2.0
/*
 * L09 - array allocations: the index table leaks when the value table cannot
 * be allocated because the shared "out" label does not free it.
 */
#include <linux/slab.h>
#include "klg_harness.h"

#define NR_KEYS 32

static noinline int table_build(void)
{
	u32 *idx;
	u64 *vals;
	int i, ret = 0;

	idx = kcalloc(NR_KEYS, sizeof(*idx), GFP_KERNEL);	/* GT:LEAK */
	if (!idx)
		return -ENOMEM;

	vals = kmalloc_array(NR_KEYS, sizeof(*vals), GFP_KERNEL);	/* GT:SAFE */
	if (!vals) {
		ret = -ENOMEM;
		goto out;		/* idx leaks: out does not free it */
	}

	for (i = 0; i < NR_KEYS; i++) {
		idx[i] = i;
		vals[i] = (u64)i * i;
	}
	kfree(vals);
	kfree(idx);
out:
	return ret;
}

KLG_TRIGGER(table_build);
KLG_SIMPLE_MODULE("KLG L09: kcalloc table leaked on kmalloc_array failure");
