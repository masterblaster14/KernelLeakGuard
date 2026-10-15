// SPDX-License-Identifier: GPL-2.0
/*
 * S03 - ownership transfer to a global list.
 * Error paths before list_add() free the item; after list_add() the list
 * owns it and module exit releases everything.
 */
#include <linux/error-injection.h>
#include <linux/list.h>
#include <linux/mutex.h>
#include <linux/slab.h>
#include "klg_harness.h"

struct item {
	struct list_head node;
	int value;
};

static LIST_HEAD(item_list);
static DEFINE_MUTEX(item_lock);
static int item_count;

static noinline int item_validate(struct item *it)
{
	return it->value > 1000 ? -ERANGE : 0;
}
ALLOW_ERROR_INJECTION(item_validate, ERRNO);

static noinline int item_add(void)
{
	struct item *it;
	int ret;

	it = kzalloc(sizeof(*it), GFP_KERNEL);	/* GT:SAFE */
	if (!it)
		return -ENOMEM;
	it->value = 42;

	ret = item_validate(it);
	if (ret) {
		kfree(it);
		return ret;
	}

	mutex_lock(&item_lock);
	list_add_tail(&it->node, &item_list);
	item_count++;
	mutex_unlock(&item_lock);
	return 0;
}

KLG_TRIGGER(item_add);

static int __init klg_s03_init(void)
{
	klg_trigger_create();
	return 0;
}

static void __exit klg_s03_exit(void)
{
	struct item *it, *tmp;

	klg_trigger_remove();
	list_for_each_entry_safe(it, tmp, &item_list, node) {
		list_del(&it->node);
		kfree(it);
	}
}

module_init(klg_s03_init);
module_exit(klg_s03_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("KLG S03: ownership transferred to a global list");
