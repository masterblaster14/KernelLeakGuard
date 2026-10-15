// SPDX-License-Identifier: GPL-2.0
/*
 * L16 - nested ownership: a buffer owned by a heap object.
 * The bind failure path frees the context but not ctx->buf. Detecting this
 * requires field-sensitive heap ownership tracking, which is out of scope of
 * the static analyser (expected false negative, see report section 5).
 */
#include <linux/error-injection.h>
#include <linux/slab.h>
#include "klg_harness.h"

struct bind_ctx {
	u8 *buf;
	int port;
};

static noinline int ctx_bind(struct bind_ctx *ctx)
{
	return ctx->port < 0 ? -EADDRINUSE : 0;
}
ALLOW_ERROR_INJECTION(ctx_bind, ERRNO);

static noinline int bind_start(void)
{
	struct bind_ctx *ctx;
	int ret;

	ctx = kzalloc(sizeof(*ctx), GFP_KERNEL);	/* GT:SAFE */
	if (!ctx)
		return -ENOMEM;

	ctx->buf = kmalloc(512, GFP_KERNEL);		/* GT:LEAK */
	if (!ctx->buf) {
		kfree(ctx);
		return -ENOMEM;
	}
	ctx->port = 80;

	ret = ctx_bind(ctx);
	if (ret) {
		kfree(ctx);		/* BUG: ctx->buf is not freed */
		return ret;
	}

	kfree(ctx->buf);
	kfree(ctx);
	return 0;
}

KLG_TRIGGER(bind_start);
KLG_SIMPLE_MODULE("KLG L16: nested buffer leaked when its owner is freed");
