// SPDX-License-Identifier: GPL-2.0
/*
 * L02 - goto cleanup ladder with a wrong label.
 * When the device name cannot be formatted the code jumps to err_rx instead
 * of err_tx, so the TX buffer is never released.
 */
#include <linux/slab.h>
#include <linux/string.h>
#include "klg_harness.h"

#define RX_SIZE 256
#define TX_SIZE 512

static noinline int sensor_program(u8 *rx, u8 *tx, const char *name)
{
	memset(rx, 0, RX_SIZE);
	memset(tx, 0xff, TX_SIZE);
	pr_debug("%s: programmed\n", name);
	return 0;
}

static noinline int sensor_setup(void)
{
	u8 *rx, *tx;
	char *name;
	int ret;

	rx = kmalloc(RX_SIZE, GFP_KERNEL);	/* GT:SAFE */
	if (!rx)
		return -ENOMEM;

	tx = kmalloc(TX_SIZE, GFP_KERNEL);	/* GT:LEAK */
	if (!tx) {
		ret = -ENOMEM;
		goto err_rx;
	}

	name = kasprintf(GFP_KERNEL, "sensor%d", 0);	/* GT:SAFE */
	if (!name) {
		ret = -ENOMEM;
		goto err_rx;		/* BUG: should be err_tx */
	}

	ret = sensor_program(rx, tx, name);
	kfree(name);
	if (ret)
		goto err_tx;
	pr_debug("sensor ready\n");
	/* success also unwinds: the buffers are scratch space */
err_tx:
	kfree(tx);
err_rx:
	kfree(rx);
	return ret;
}

KLG_TRIGGER(sensor_setup);
KLG_SIMPLE_MODULE("KLG L02: goto ladder jumps past a cleanup label");
