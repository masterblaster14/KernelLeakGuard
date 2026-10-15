// SPDX-License-Identifier: GPL-2.0
/*
 * S06 - device-managed allocations (init mode).
 * devm_* memory is released automatically by the driver core when probe
 * fails or the device is unbound, so early returns in probe are correct.
 */
#include <linux/err.h>
#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/slab.h>

struct demo_priv {
	u8 *buf;
	int irq;
};

static int demo_probe(struct platform_device *pdev)
{
	struct demo_priv *priv;

	priv = devm_kzalloc(&pdev->dev, sizeof(*priv), GFP_KERNEL);	/* GT:SAFE */
	if (!priv)
		return -ENOMEM;

	priv->buf = devm_kmalloc(&pdev->dev, 512, GFP_KERNEL);	/* GT:SAFE */
	if (!priv->buf)
		return -ENOMEM;

	platform_set_drvdata(pdev, priv);
	return 0;
}

static struct platform_driver demo_driver = {
	.probe = demo_probe,
	.driver = { .name = "klg_s06_demo" },
};

static struct platform_device *demo_pdev;

static int __init klg_s06_init(void)
{
	int ret;

	ret = platform_driver_register(&demo_driver);
	if (ret)
		return ret;

	demo_pdev = platform_device_register_simple("klg_s06_demo", -1, NULL, 0);
	if (IS_ERR(demo_pdev)) {
		platform_driver_unregister(&demo_driver);
		return PTR_ERR(demo_pdev);
	}
	return 0;
}

static void __exit klg_s06_exit(void)
{
	platform_device_unregister(demo_pdev);
	platform_driver_unregister(&demo_driver);
}

module_init(klg_s06_init);
module_exit(klg_s06_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("KLG S06: managed (devm) allocations in probe");
