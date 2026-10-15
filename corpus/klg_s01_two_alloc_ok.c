// SPDX-License-Identifier: GPL-2.0
/*
 * S01 - fixed version of L01 (init mode): every exit releases what it owns.
 */
#include <linux/module.h>
#include <linux/slab.h>
#include <linux/string.h>

static noinline int initialize(void)
{
	char *a, *b;

	a = kmalloc(100, GFP_KERNEL);	/* GT:SAFE */
	if (!a)
		return -ENOMEM;
	b = kmalloc(200, GFP_KERNEL);	/* GT:SAFE */
	if (!b) {
		kfree(a);
		return -ENOMEM;
	}

	memset(a, 0, 100);
	memset(b, 0, 200);
	kfree(b);
	kfree(a);
	return 0;
}

static int __init klg_s01_init(void)
{
	return initialize();
}

static void __exit klg_s01_exit(void)
{
}

module_init(klg_s01_init);
module_exit(klg_s01_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("KLG S01: correct two-allocation init");
