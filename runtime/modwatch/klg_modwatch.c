// SPDX-License-Identifier: GPL-2.0
/*
 * klg_modwatch - log where modules are loaded, for KernelLeakGuard.
 *
 * When a module's initialisation fails, the kernel frees the module before
 * kmemleak prints its report, so allocation backtraces through the module
 * show raw addresses instead of symbols. This helper registers a module
 * notifier and, whenever a module enters MODULE_STATE_COMING (loaded and
 * relocated, about to run its init function), logs
 *
 *   KLG-MOD <name> text=<base>+<size> init=<base>+<size>
 *
 * and, the first time a given layout is seen, the final address of every
 * function symbol of the module:
 *
 *   KLG-SYM <name> <address> <symbol>
 *
 * The host uses these lines to turn raw return addresses back into
 * symbol+offset and then into source lines.
 */
#include <linux/kallsyms.h>
#include <linux/module.h>
#include <linux/notifier.h>
#include <linux/rcupdate.h>
#include <linux/string.h>

#define MAX_SEEN 512

struct seen_layout {
	char name[MODULE_NAME_LEN];
	void *text;
	void *init;
};

static struct seen_layout seen[MAX_SEEN];
static unsigned int nr_seen;
static DEFINE_MUTEX(seen_lock);

/* True if this exact (module, text base, init base) was already dumped. */
static bool layout_seen(struct module *mod, void *text, void *init)
{
	unsigned int i;

	for (i = 0; i < nr_seen; i++)
		if (seen[i].text == text && seen[i].init == init &&
		    !strcmp(seen[i].name, mod->name))
			return true;
	if (nr_seen < MAX_SEEN) {
		strscpy(seen[nr_seen].name, mod->name, MODULE_NAME_LEN);
		seen[nr_seen].text = text;
		seen[nr_seen].init = init;
		nr_seen++;
	}
	return false;
}

static void dump_symbols(struct module *mod)
{
	struct mod_kallsyms *ks;
	unsigned int i;

	rcu_read_lock();
	ks = rcu_dereference(mod->kallsyms);
	for (i = 0; ks && i < ks->num_symtab; i++) {
		const Elf_Sym *sym = &ks->symtab[i];
		char type = ks->typetab[i];

		if ((type != 't' && type != 'T') || !sym->st_value)
			continue;
		pr_info("KLG-SYM %s %px %s\n", mod->name, (void *)sym->st_value,
			ks->strtab + sym->st_name);
	}
	rcu_read_unlock();
}

static int klg_modwatch_event(struct notifier_block *nb, unsigned long action, void *data)
{
	struct module *mod = data;
	void *text, *init;

	if (action != MODULE_STATE_COMING || mod == THIS_MODULE)
		return NOTIFY_DONE;

	text = mod->mem[MOD_TEXT].base;
	init = mod->mem[MOD_INIT_TEXT].base;
	pr_info("KLG-MOD %s text=%px+%x init=%px+%x\n", mod->name,
		text, mod->mem[MOD_TEXT].size, init, mod->mem[MOD_INIT_TEXT].size);

	mutex_lock(&seen_lock);
	if (!layout_seen(mod, text, init))
		dump_symbols(mod);
	mutex_unlock(&seen_lock);
	return NOTIFY_OK;
}

static struct notifier_block klg_modwatch_nb = {
	.notifier_call = klg_modwatch_event,
};

static int __init klg_modwatch_init(void)
{
	return register_module_notifier(&klg_modwatch_nb);
}

static void __exit klg_modwatch_exit(void)
{
	unregister_module_notifier(&klg_modwatch_nb);
}

module_init(klg_modwatch_init);
module_exit(klg_modwatch_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("KernelLeakGuard: log module load addresses and symbols");
