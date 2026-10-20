/* Analyser regression cases for patterns found on real kernel code.
 * Compiled like kbuild compiles modules for IR: clang -O2 -g -emit-llvm
 * -Xclang -disable-llvm-passes. Kernel APIs are declared, not included.
 */
void *kmalloc(unsigned long size, int flags);
void kfree(const void *p);
int may_fail(void);
int fill(char *buf);
void consume(void *p);

/* 1. One return of phi(obj, NULL): the may_fail() path returns NULL without
 *    freeing p (null_alloc_dev() pattern). Must be reported. */
void *phi_return_leak(void)
{
	void *p = kmalloc(64, 0);

	if (!p)
		return 0;
	if (may_fail())
		return 0;
	return p;
}

/* 2. goto out of a scoped block: clang emits a cleanup-destination switch whose
 *    default edge cannot execute. Every real path frees p: no report. */
int scoped_goto_ok(void)
{
	int ret;
	char *p = kmalloc(64, 0);

	if (!p)
		return -12;
	{
		char buf[16];

		ret = fill(buf);
		if (ret)
			goto out;
		consume(buf);
	}
	kfree(p);
	return 0;
out:
	kfree(p);
	return ret;
}

/* 3. A helper that publishes the object before returning it is a lookup: the
 *    caller does not own the result, so no report in use_lookup(). */
static void *registry;

static __attribute__((noinline)) void *lookup_or_create(void)
{
	void *p = kmalloc(64, 0);

	if (!p)
		return 0;
	registry = p;
	return p;
}

int use_lookup(void)
{
	void *o = lookup_or_create();

	if (!o)
		return -12;
	if (may_fail())
		return -22;
	consume(o);
	return 0;
}

/* 4. Storing the object into a scratch buffer the helper frees again does not
 *    publish it: make_table() is an allocation wrapper and use_table() leaks. */
static __attribute__((noinline)) void *make_table(void)
{
	void *t = kmalloc(64, 0);
	void **scratch;

	if (!t)
		return 0;
	scratch = kmalloc(sizeof(void *), 0);
	if (scratch) {
		scratch[0] = t;
		kfree(scratch);
	}
	return t;
}

int use_table(void)
{
	void *o = make_table();

	if (!o)
		return -12;
	if (may_fail())
		return -22;
	consume(o);
	return 0;
}

/* 5. return from inside a loop body with a scoped local: the cleanup
 *    destination has a single case, so kbuild-style IR folds the switch into
 *    a branch on (dest == continue). Returning pcl is a hand-over: no report. */
struct slab { void *cache; unsigned int max; };
static struct slab pool[3];

void *loop_return_ok(unsigned int n)
{
	struct slab *pcs = pool;

	for (; pcs < pool + 3; ++pcs) {
		void *pcl;

		if (n > pcs->max)
			continue;
		pcl = kmalloc(64, 0);
		if (!pcl)
			return (void *)-12L;
		return pcl;
	}
	return (void *)-22L;
}

/* 6. register_netdevice() takes ownership only when it succeeds; on failure
 *    the caller must free_netdev(). Bonding shipped this bug until commit
 *    8d6184e4881b ("bonding: fix device leak on error in bond_create()"). */
struct net_device;
struct net_device *alloc_netdev_mqs(int sizeof_priv, const char *name,
				    unsigned char name_assign_type,
				    void (*setup)(struct net_device *),
				    unsigned int txqs, unsigned int rxqs);
int register_netdevice(struct net_device *dev);
void free_netdev(struct net_device *dev);

int netdev_create_leak(void)
{
	struct net_device *dev = alloc_netdev_mqs(0, "d%d", 0, 0, 1, 1);
	int res;

	if (!dev)
		return -12;
	res = register_netdevice(dev);
	if (res < 0)
		goto out;		/* missing free_netdev() */
	consume(dev);
out:
	return res;
}

int netdev_create_ok(void)
{
	struct net_device *dev = alloc_netdev_mqs(0, "d%d", 0, 0, 1, 1);
	int res;

	if (!dev)
		return -12;
	res = register_netdevice(dev);
	if (res < 0)
		free_netdev(dev);
	return res;
}
