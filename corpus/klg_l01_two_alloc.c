// SPDX-License-Identifier: GPL-2.0
/*
 * L01 - the canonical early-exit leak (init mode).
 * The second allocation's failure path returns without releasing the first.
 */
#include <linux/module.h>
#include <linux/slab.h>
#include <linux/string.h>

static noinline int initialize(void)
{
	char *a, *b;

	a = kmalloc(100, GFP_KERNEL);	/* GT:LEAK */
	if (!a)
		return -ENOMEM;
	b = kmalloc(200, GFP_KERNEL);	/* GT:SAFE */
	if (!b)
		return -ENOMEM;		/* a leaks here */

	memset(a, 0, 100);
	memset(b, 0, 200);
	kfree(b);
	kfree(a);
	return 0;
}

static int __init klg_l01_init(void)
{
	return initialize();
}

static void __exit klg_l01_exit(void)
{
}

module_init(klg_l01_init);
module_exit(klg_l01_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("KLG L01: leak on second allocation failure in module init");
