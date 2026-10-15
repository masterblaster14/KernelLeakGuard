// SPDX-License-Identifier: GPL-2.0
/*
 * S02 - correct goto cleanup ladder (fixed version of L02).
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

	tx = kmalloc(TX_SIZE, GFP_KERNEL);	/* GT:SAFE */
	if (!tx) {
		ret = -ENOMEM;
		goto err_rx;
	}

	name = kasprintf(GFP_KERNEL, "sensor%d", 0);	/* GT:SAFE */
	if (!name) {
		ret = -ENOMEM;
		goto err_tx;
	}

	ret = sensor_program(rx, tx, name);
	kfree(name);
err_tx:
	kfree(tx);
err_rx:
	kfree(rx);
	return ret;
}

KLG_TRIGGER(sensor_setup);
KLG_SIMPLE_MODULE("KLG S02: correct goto ladder");
