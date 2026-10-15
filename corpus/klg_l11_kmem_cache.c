// SPDX-License-Identifier: GPL-2.0
/*
 * L11 - object from a dedicated slab cache leaked on a later failure.
 */
#include <linux/slab.h>
#include <linux/string.h>
#include "klg_harness.h"

struct io_req {
	u64 sector;
	u32 len;
	u32 flags;
};

static struct kmem_cache *req_cache;

static noinline int req_submit(void)
{
	struct io_req *req;
	u8 *payload;

	req = kmem_cache_alloc(req_cache, GFP_KERNEL);	/* GT:LEAK */
	if (!req)
		return -ENOMEM;

	payload = kzalloc(256, GFP_KERNEL);	/* GT:SAFE */
	if (!payload)
		return -ENOMEM;		/* req leaks here */

	req->sector = 8;
	req->len = 256;
	memset(payload, 0xa5, 256);
	kfree(payload);
	kmem_cache_free(req_cache, req);
	return 0;
}

KLG_TRIGGER(req_submit);

static int __init klg_l11_init(void)
{
	req_cache = kmem_cache_create("klg_io_req", sizeof(struct io_req), 0, 0, NULL);
	if (!req_cache)
		return -ENOMEM;
	klg_trigger_create();
	return 0;
}

static void __exit klg_l11_exit(void)
{
	klg_trigger_remove();
	kmem_cache_destroy(req_cache);
}

module_init(klg_l11_init);
module_exit(klg_l11_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("KLG L11: kmem_cache object leaked on payload failure");
