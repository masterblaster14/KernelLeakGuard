// SPDX-License-Identifier: GPL-2.0
/*
 * L07 - interprocedural: the normal path releases through a wrapper.
 * ctx_release() frees the context on success, but the early exit taken when
 * the scratch buffer cannot be allocated forgets to call it.
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

	c = kzalloc(sizeof(*c), GFP_KERNEL);	/* GT:LEAK */
	if (!c)
		return -ENOMEM;

	scratch = kmalloc(1024, GFP_KERNEL);	/* GT:SAFE */
	if (!scratch)
		return -ENOMEM;		/* c leaks: ctx_release() not called */

	memset(scratch, 0, 1024);
	c->done = 1024;
	kfree(scratch);
	ctx_release(c);
	return 0;
}

KLG_TRIGGER(xfer_run);
KLG_SIMPLE_MODULE("KLG L07: error path skips a release wrapper");
