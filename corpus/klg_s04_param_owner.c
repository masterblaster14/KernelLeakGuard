// SPDX-License-Identifier: GPL-2.0
/*
 * S04 - ownership transfer to the caller through a parameter's field.
 * attach_buffer() stores the buffer in port->buf before a later check can
 * fail; the caller is responsible for releasing it in that case.
 */
#include <linux/error-injection.h>
#include <linux/slab.h>
#include <linux/string.h>
#include "klg_harness.h"

struct port {
	u8 *buf;
	size_t size;
};

static struct port the_port;

static noinline int port_check(struct port *p)
{
	return p->size > 4096 ? -EINVAL : 0;
}
ALLOW_ERROR_INJECTION(port_check, ERRNO);

static noinline int attach_buffer(struct port *p)
{
	u8 *buf;

	buf = kmalloc(512, GFP_KERNEL);		/* GT:SAFE */
	if (!buf)
		return -ENOMEM;
	p->buf = buf;
	p->size = 512;

	return port_check(p);		/* on error the caller frees p->buf */
}

static noinline int port_open(void)
{
	struct port *p = &the_port;
	int ret;

	ret = attach_buffer(p);
	if (ret) {
		kfree(p->buf);
		p->buf = NULL;
		return ret;
	}

	memset(p->buf, 0, p->size);
	kfree(p->buf);
	p->buf = NULL;
	return 0;
}

KLG_TRIGGER(port_open);
KLG_SIMPLE_MODULE("KLG S04: ownership transferred to caller-owned structure");
