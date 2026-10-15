// SPDX-License-Identifier: GPL-2.0
/*
 * S08 - pointers kept in a stack-allocated structure, released correctly
 * (fixed L17).
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

	ws.in = kmalloc(ws.len, GFP_KERNEL);	/* GT:SAFE */
	if (!ws.in)
		return -ENOMEM;

	ws.out = kmalloc(ws.len, GFP_KERNEL);	/* GT:SAFE */
	if (!ws.out) {
		kfree(ws.in);
		return -ENOMEM;
	}

	memset(ws.in, 1, ws.len);
	memcpy(ws.out, ws.in, ws.len);
	kfree(ws.out);
	kfree(ws.in);
	return 0;
}

KLG_TRIGGER(transform_run);
KLG_SIMPLE_MODULE("KLG S08: local struct buffers released on all paths");
