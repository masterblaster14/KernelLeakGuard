// SPDX-License-Identifier: GPL-2.0
/*
 * L13 - module init leaks its table when misc_register() fails (init mode).
 * On success ownership moves to a global and module exit frees it.
 */
#include <linux/fs.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/slab.h>

struct led_table {
	u8 level[16];
	u32 mask;
};

static struct led_table *ledctl_tbl;

static const struct file_operations ledctl_fops = {
	.owner = THIS_MODULE,
};

static struct miscdevice ledctl_dev = {
	.minor = MISC_DYNAMIC_MINOR,
	.name = "klg_ledctl",
	.fops = &ledctl_fops,
};

static noinline void led_table_fill(struct led_table *tbl)
{
	int i;

	for (i = 0; i < 16; i++)
		tbl->level[i] = i * 16;
	tbl->mask = 0xffff;
}

static int __init ledctl_init(void)
{
	struct led_table *tbl;
	int ret;

	tbl = kzalloc(sizeof(*tbl), GFP_KERNEL);	/* GT:LEAK */
	if (!tbl)
		return -ENOMEM;
	led_table_fill(tbl);

	ret = misc_register(&ledctl_dev);
	if (ret)
		return ret;		/* tbl leaks here */

	ledctl_tbl = tbl;
	return 0;
}

static void __exit ledctl_exit(void)
{
	misc_deregister(&ledctl_dev);
	kfree(ledctl_tbl);
}

module_init(ledctl_init);
module_exit(ledctl_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("KLG L13: init leaks when misc_register fails");
