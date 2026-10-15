// SPDX-License-Identifier: GPL-2.0
/*
 * L10 - vmalloc'd firmware image leaked when the header allocation fails.
 */
#include <linux/slab.h>
#include <linux/string.h>
#include <linux/vmalloc.h>
#include "klg_harness.h"

#define FW_SIZE (64 * 1024)

struct fw_header {
	u32 magic;
	u32 len;
};

static noinline int fw_stage(void)
{
	struct fw_header *hdr;
	u8 *fw;

	fw = vmalloc(FW_SIZE);			/* GT:LEAK */
	if (!fw)
		return -ENOMEM;

	hdr = kzalloc(sizeof(*hdr), GFP_KERNEL);	/* GT:SAFE */
	if (!hdr)
		return -ENOMEM;		/* fw leaks here */

	memset(fw, 0, FW_SIZE);
	hdr->magic = 0x4b4c47;
	hdr->len = FW_SIZE;
	kfree(hdr);
	vfree(fw);
	return 0;
}

KLG_TRIGGER(fw_stage);
KLG_SIMPLE_MODULE("KLG L10: vmalloc buffer leaked on kzalloc failure");
