// SPDX-License-Identifier: GPL-2.0
/*
 * S05 - factory function returning freshly allocated memory; the caller
 * releases it on every path.
 */
#include <linux/slab.h>
#include <linux/string.h>
#include "klg_harness.h"

static noinline char *make_label(int id)
{
	return kasprintf(GFP_KERNEL, "label-%d", id);	/* GT:SAFE */
}

static noinline int label_use(void)
{
	char *label, *tmp;

	label = make_label(1);			/* GT:SAFE */
	if (!label)
		return -ENOMEM;

	tmp = kmalloc(32, GFP_KERNEL);		/* GT:SAFE */
	if (!tmp) {
		kfree(label);
		return -ENOMEM;
	}

	strscpy(tmp, label, 32);
	kfree(tmp);
	kfree(label);
	return 0;
}

KLG_TRIGGER(label_use);
KLG_SIMPLE_MODULE("KLG S05: allocation returned by a factory and freed by caller");
