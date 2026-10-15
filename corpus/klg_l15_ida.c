// SPDX-License-Identifier: GPL-2.0
/*
 * L15 - device object leaked when ID allocation fails.
 */
#include <linux/idr.h>
#include <linux/slab.h>
#include "klg_harness.h"

struct widget {
	int id;
	char name[24];
};

static DEFINE_IDA(widget_ida);

static noinline int widget_add(void)
{
	struct widget *w;
	int id;

	w = kzalloc(sizeof(*w), GFP_KERNEL);	/* GT:LEAK */
	if (!w)
		return -ENOMEM;

	id = ida_alloc(&widget_ida, GFP_KERNEL);
	if (id < 0)
		return id;		/* w leaks here */

	w->id = id;
	snprintf(w->name, sizeof(w->name), "widget%d", id);
	ida_free(&widget_ida, id);
	kfree(w);
	return 0;
}

KLG_TRIGGER(widget_add);

static int __init klg_l15_init(void)
{
	klg_trigger_create();
	return 0;
}

static void __exit klg_l15_exit(void)
{
	klg_trigger_remove();
	ida_destroy(&widget_ida);
}

module_init(klg_l15_init);
module_exit(klg_l15_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("KLG L15: object leaked when ida_alloc fails");
