// SPDX-License-Identifier: GPL-2.0
/*
 * L05 - leak when copy_from_user() fails (a very common real-world pattern).
 * The fix is to free the buffer, or use memdup_user_nul().
 */
#include <linux/slab.h>
#include <linux/uaccess.h>
#include "klg_harness.h"

static unsigned long cfg_value;

static noinline ssize_t cfg_store(const char __user *ubuf, size_t len)
{
	char *kbuf;
	int ret;

	if (len > 64)
		return -EINVAL;

	kbuf = kmalloc(len + 1, GFP_KERNEL);	/* GT:LEAK */
	if (!kbuf)
		return -ENOMEM;

	if (copy_from_user(kbuf, ubuf, len))
		return -EFAULT;		/* kbuf leaks here */
	kbuf[len] = '\0';

	ret = kstrtoul(kbuf, 0, &cfg_value);
	kfree(kbuf);
	return ret ? ret : len;
}

KLG_TRIGGER_USER(cfg_store);
KLG_SIMPLE_MODULE("KLG L05: leak on copy_from_user failure");
