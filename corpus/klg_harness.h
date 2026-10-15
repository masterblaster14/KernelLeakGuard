/* SPDX-License-Identifier: GPL-2.0 */
/*
 * klg_harness.h - minimal test harness shared by the KernelLeakGuard corpus.
 *
 * A corpus module exposes the kernel routine under test through a debugfs
 * file /sys/kernel/debug/klg_<module>. Writing to the file runs the routine
 * once in the writer's task context, which lets the runtime verifier arm
 * per-task fault injection (fail-nth) right before the call.
 *
 * Ground-truth annotations used by the evaluator (one per allocation site):
 *   GT:LEAK  - this allocation leaks on at least one early-exit path
 *   GT:SAFE  - this allocation is always released or handed over
 */
#ifndef KLG_HARNESS_H
#define KLG_HARNESS_H

#include <linux/debugfs.h>
#include <linux/fs.h>
#include <linux/module.h>

/* Routine without arguments: int fn(void). */
#define KLG_TRIGGER(fn)							\
static ssize_t klg_trigger_write(struct file *f, const char __user *u,	\
				 size_t len, loff_t *off)		\
{									\
	int ret = fn();							\
	return ret < 0 ? ret : (ssize_t)len;				\
}									\
KLG_TRIGGER_FILE()

/* Routine consuming the user buffer: ssize_t fn(const char __user *, size_t). */
#define KLG_TRIGGER_USER(fn)						\
static ssize_t klg_trigger_write(struct file *f, const char __user *u,	\
				 size_t len, loff_t *off)		\
{									\
	ssize_t ret = fn(u, len);					\
	return ret < 0 ? ret : (ssize_t)len;				\
}									\
KLG_TRIGGER_FILE()

#define KLG_TRIGGER_FILE()						\
static const struct file_operations klg_trigger_fops = {		\
	.owner = THIS_MODULE,						\
	.write = klg_trigger_write,					\
};									\
static struct dentry *klg_trigger_dentry;				\
static inline void klg_trigger_create(void)				\
{									\
	klg_trigger_dentry = debugfs_create_file("klg_" KBUILD_MODNAME,	\
			0200, NULL, NULL, &klg_trigger_fops);		\
}									\
static inline void klg_trigger_remove(void)				\
{									\
	debugfs_remove(klg_trigger_dentry);				\
}

/* Standard init/exit for trigger-mode modules without extra state. */
#define KLG_SIMPLE_MODULE(desc)						\
static int __init klg_mod_init(void)					\
{									\
	klg_trigger_create();						\
	return 0;							\
}									\
static void __exit klg_mod_exit(void)					\
{									\
	klg_trigger_remove();						\
}									\
module_init(klg_mod_init);						\
module_exit(klg_mod_exit);						\
MODULE_LICENSE("GPL");							\
MODULE_DESCRIPTION(desc)

#endif /* KLG_HARNESS_H */
