// SPDX-License-Identifier: GPL-2.0
/*
 * S11 - ownership handed to a registry function before a later failure.
 * table_insert() links the entry into a global table, so the early return
 * after a failed resize is not a leak.
 */
#include <linux/error-injection.h>
#include <linux/slab.h>
#include "klg_harness.h"

struct entry {
	struct entry *next;
	int key;
};

static struct entry *table_head;
static int table_size = 8;

static noinline void table_insert(struct entry *e)
{
	e->next = table_head;
	table_head = e;
}

static noinline int table_resize(void)
{
	return table_size > 1024 ? -ENOSPC : 0;
}
ALLOW_ERROR_INJECTION(table_resize, ERRNO);

static noinline int entry_add(void)
{
	struct entry *e;
	int ret;

	e = kzalloc(sizeof(*e), GFP_KERNEL);	/* GT:SAFE */
	if (!e)
		return -ENOMEM;
	e->key = 5;
	table_insert(e);

	ret = table_resize();
	if (ret)
		return ret;	/* e is owned by the table */

	table_size++;
	return 0;
}

KLG_TRIGGER(entry_add);

static int __init klg_s11_init(void)
{
	klg_trigger_create();
	return 0;
}

static void __exit klg_s11_exit(void)
{
	struct entry *e;

	klg_trigger_remove();
	while ((e = table_head)) {
		table_head = e->next;
		kfree(e);
	}
}

module_init(klg_s11_init);
module_exit(klg_s11_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("KLG S11: ownership transferred through a registry helper");
