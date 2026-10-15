// SPDX-License-Identifier: GPL-2.0
/*
 * L14 - conditionally allocated histogram leaked when calibration fails.
 */
#include <linux/error-injection.h>
#include <linux/slab.h>
#include "klg_harness.h"

#define NR_SAMPLES 64

static bool want_histogram = true;

static noinline int stats_calibrate(u32 *samples)
{
	return samples[0] == 0xdead ? -EIO : 0;
}
ALLOW_ERROR_INJECTION(stats_calibrate, ERRNO);

static noinline int stats_setup(void)
{
	u32 *samples, *hist = NULL;
	int ret;

	samples = kcalloc(NR_SAMPLES, sizeof(*samples), GFP_KERNEL);	/* GT:SAFE */
	if (!samples)
		return -ENOMEM;

	if (want_histogram) {
		hist = kzalloc(256 * sizeof(*hist), GFP_KERNEL);	/* GT:LEAK */
		if (!hist) {
			kfree(samples);
			return -ENOMEM;
		}
	}

	ret = stats_calibrate(samples);
	if (ret) {
		kfree(samples);
		return ret;		/* hist leaks here */
	}

	kfree(hist);
	kfree(samples);
	return 0;
}

KLG_TRIGGER(stats_setup);
KLG_SIMPLE_MODULE("KLG L14: conditional allocation leaked on calibration error");
