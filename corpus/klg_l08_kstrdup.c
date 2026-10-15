// SPDX-License-Identifier: GPL-2.0
/*
 * L08 - leak of memory returned by kstrdup() when kmemdup() fails.
 */
#include <linux/slab.h>
#include <linux/string.h>
#include "klg_harness.h"

static const u8 profile_template[48] = { 0x4b, 0x4c, 0x47 };

static noinline int profile_load(void)
{
	char *label;
	u8 *blob;

	label = kstrdup("default-profile", GFP_KERNEL);	/* GT:LEAK */
	if (!label)
		return -ENOMEM;

	blob = kmemdup(profile_template, sizeof(profile_template), GFP_KERNEL);	/* GT:SAFE */
	if (!blob)
		return -ENOMEM;		/* label leaks here */

	pr_debug("profile %s: %*ph\n", label, 3, blob);
	kfree(blob);
	kfree(label);
	return 0;
}

KLG_TRIGGER(profile_load);
KLG_SIMPLE_MODULE("KLG L08: kstrdup result leaked on kmemdup failure");
