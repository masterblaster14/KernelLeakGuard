// SPDX-License-Identifier: GPL-2.0
/*
 * S14 - reference-counted object released through kref_put() and a release
 * callback on the error path.
 */
#include <linux/error-injection.h>
#include <linux/kref.h>
#include <linux/slab.h>
#include "klg_harness.h"

struct conn {
	struct kref ref;
	int fd;
};

static void conn_release(struct kref *ref)
{
	kfree(container_of(ref, struct conn, ref));
}

static noinline int conn_handshake(struct conn *c)
{
	return c->fd < 0 ? -ECONNREFUSED : 0;
}
ALLOW_ERROR_INJECTION(conn_handshake, ERRNO);

static noinline int conn_open(void)
{
	struct conn *c;
	int ret;

	c = kzalloc(sizeof(*c), GFP_KERNEL);	/* GT:SAFE */
	if (!c)
		return -ENOMEM;
	kref_init(&c->ref);
	c->fd = 4;

	ret = conn_handshake(c);
	if (ret) {
		kref_put(&c->ref, conn_release);
		return ret;
	}

	kref_put(&c->ref, conn_release);
	return 0;
}

KLG_TRIGGER(conn_open);
KLG_SIMPLE_MODULE("KLG S14: kref release callback on error path");
