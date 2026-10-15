// SPDX-License-Identifier: GPL-2.0
/*
 * L17 - pointers kept in a stack-allocated structure.
 * When the output buffer cannot be allocated, the input buffer stored in the
 * local struct is not released.
 */
#include <linux/slab.h>
#include <linux/string.h>
#include "klg_harness.h"

struct work_set {
	u8 *in;
	u8 *out;
	size_t len;
};

static noinline int transform_run(void)
{
	struct work_set ws = { .len = 256 };

	ws.in = kmalloc(ws.len, GFP_KERNEL);	/* GT:LEAK */
	if (!ws.in)
		return -ENOMEM;

	ws.out = kmalloc(ws.len, GFP_KERNEL);	/* GT:SAFE */
	if (!ws.out)
		return -ENOMEM;		/* ws.in leaks here */

	memset(ws.in, 1, ws.len);
	memcpy(ws.out, ws.in, ws.len);
	kfree(ws.out);
	kfree(ws.in);
	return 0;
}

KLG_TRIGGER(transform_run);
KLG_SIMPLE_MODULE("KLG L17: buffer stored in a local struct leaked");
