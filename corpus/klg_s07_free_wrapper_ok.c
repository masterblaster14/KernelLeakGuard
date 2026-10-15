// SPDX-License-Identifier: GPL-2.0
/*
 * S07 - release wrapper used consistently on all paths (fixed L07).
 */
#include <linux/slab.h>
#include <linux/string.h>
#include "klg_harness.h"

struct xfer_ctx {
	int state;
	size_t done;
};

static noinline void ctx_release(struct xfer_ctx *c)
{
	c->state = -1;
	kfree(c);
}

static noinline int xfer_run(void)
{
	struct xfer_ctx *c;
	u8 *scratch;

	c = kzalloc(sizeof(*c), GFP_KERNEL);	/* GT:SAFE */
	if (!c)
		return -ENOMEM;

	scratch = kmalloc(1024, GFP_KERNEL);	/* GT:SAFE */
	if (!scratch) {
		ctx_release(c);
		return -ENOMEM;
	}

	memset(scratch, 0, 1024);
	c->done = 1024;
	kfree(scratch);
	ctx_release(c);
	return 0;
}

KLG_TRIGGER(xfer_run);
KLG_SIMPLE_MODULE("KLG S07: release wrapper on every path");
