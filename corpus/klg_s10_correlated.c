// SPDX-License-Identifier: GPL-2.0
/*
 * S10 - allocation and release guarded by the same condition.
 * A path-insensitive analysis sees a path "allocate, then skip kfree";
 * that path is infeasible because both branches test the same value.
 */
#include <linux/slab.h>
#include <linux/string.h>
#include "klg_harness.h"

static int trace_level = 2;

static noinline int trace_dump(void)
{
	char *line = NULL;
	int verbose = trace_level > 1;

	if (verbose) {
		line = kmalloc(128, GFP_KERNEL);	/* GT:SAFE */
		if (!line)
			return -ENOMEM;
		snprintf(line, 128, "level=%d", trace_level);
	}

	pr_debug("trace dump%s\n", verbose ? " (verbose)" : "");

	if (verbose)
		kfree(line);
	return 0;
}

KLG_TRIGGER(trace_dump);
KLG_SIMPLE_MODULE("KLG S10: correlated allocate/free conditions");
