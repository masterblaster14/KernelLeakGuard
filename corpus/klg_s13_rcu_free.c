// SPDX-License-Identifier: GPL-2.0
/*
 * S13 - deferred release through RCU on the error path.
 * kfree_rcu() and call_rcu() free the object after a grace period, which a
 * naive "missing kfree" check would miss.
 */
#include <linux/error-injection.h>
#include <linux/rcupdate.h>
#include <linux/slab.h>
#include "klg_harness.h"

struct route {
	struct rcu_head rcu;
	u32 dst;
	u32 gw;
};

static noinline int route_check(struct route *r)
{
	return r->dst == 0 ? -EHOSTUNREACH : 0;
}
ALLOW_ERROR_INJECTION(route_check, ERRNO);

static void route_free_cb(struct rcu_head *head)
{
	kfree(container_of(head, struct route, rcu));
}

static noinline int route_add(void)
{
	struct route *r, *backup;
	int ret;

	r = kzalloc(sizeof(*r), GFP_KERNEL);		/* GT:SAFE */
	if (!r)
		return -ENOMEM;
	r->dst = 0x0a000001;

	backup = kzalloc(sizeof(*backup), GFP_KERNEL);	/* GT:SAFE */
	if (!backup) {
		kfree_rcu(r, rcu);
		return -ENOMEM;
	}

	ret = route_check(r);
	if (ret) {
		call_rcu(&backup->rcu, route_free_cb);
		kfree_rcu(r, rcu);
		return ret;
	}

	kfree(backup);
	kfree(r);
	return 0;
}

KLG_TRIGGER(route_add);

static int __init klg_s13_init(void)
{
	klg_trigger_create();
	return 0;
}

static void __exit klg_s13_exit(void)
{
	klg_trigger_remove();
	rcu_barrier();	/* wait for pending callbacks before code goes away */
}

module_init(klg_s13_init);
module_exit(klg_s13_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("KLG S13: RCU-deferred release on error paths");
