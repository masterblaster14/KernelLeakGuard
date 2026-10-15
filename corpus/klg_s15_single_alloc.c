// SPDX-License-Identifier: GPL-2.0
/*
 * S15 - a single allocation whose only early exit is its own failure.
 * Returning on allocation failure is not a leak (nothing was allocated).
 */
#include <linux/slab.h>
#include <linux/string.h>
#include "klg_harness.h"

static noinline int scratch_use(void)
{
	char *buf;

	buf = kzalloc(4096, GFP_KERNEL);	/* GT:SAFE */
	if (!buf)
		return -ENOMEM;

	strscpy(buf, "klg", 4096);
	kfree(buf);
	return 0;
}

KLG_TRIGGER(scratch_use);
KLG_SIMPLE_MODULE("KLG S15: single allocation, failure check only");
