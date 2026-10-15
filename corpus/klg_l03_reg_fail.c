// SPDX-License-Identifier: GPL-2.0
/*
 * L03 - leak on a non-allocation error.
 * Registering the channel with the (simulated) hardware can fail; the error
 * is propagated without freeing the channel object. hw_register_channel()
 * is marked error-injectable so the fault can be triggered with fail_function.
 */
#include <linux/error-injection.h>
#include <linux/slab.h>
#include "klg_harness.h"

struct channel {
	int id;
	u32 flags;
};

static noinline int hw_register_channel(struct channel *ch)
{
	return ch->id < 0 ? -EINVAL : 0;
}
ALLOW_ERROR_INJECTION(hw_register_channel, ERRNO);

static noinline void hw_unregister_channel(struct channel *ch)
{
	ch->flags = 0;
}

static noinline int channel_open(void)
{
	struct channel *ch;
	int ret;

	ch = kzalloc(sizeof(*ch), GFP_KERNEL);	/* GT:LEAK */
	if (!ch)
		return -ENOMEM;
	ch->id = 3;

	ret = hw_register_channel(ch);
	if (ret)
		return ret;		/* ch leaks here */

	ch->flags = 1;
	hw_unregister_channel(ch);
	kfree(ch);
	return 0;
}

KLG_TRIGGER(channel_open);
KLG_SIMPLE_MODULE("KLG L03: leak when hardware registration fails");
