// SPDX-License-Identifier: GPL-2.0
/*
 * klg-agent - KernelLeakGuard in-guest fault-injection driver.
 *
 * Runs inside the QEMU guest. For a target kernel code path it repeatedly
 * arms the per-task fault injector (/proc/thread-self/fail-nth) so that the
 * N-th fault point (slab allocation, user copy, error-injectable function)
 * fails, executes the path, and records what happened together with the
 * kernel log lines emitted during that attempt (fault-injection stack traces).
 *
 * Target paths:
 *   trigger mode : write "1" to a debugfs trigger file exported by a module
 *   init mode    : load a .ko with finit_module(); its module_init runs
 *
 * Commands:
 *   klg-agent sweep  --mode M --target T [--max N] [--start N] [--filter MOD]
 *                    [--out FILE]
 *       N = 1, 2, 3, ... until the path executes without consuming the fault
 *       (all fault points visited) or --max is reached. With --filter only
 *       fault points that have module MOD on their call stack are counted.
 *   klg-agent repeat --mode M --target T --nth N --count R
 *                    [--expect FRAME [--window W]] [--out FILE]
 *       Execute the path R times, each time failing the N-th fault point
 *       (N = 0 runs the path without injection - control run). With
 *       --expect, an attempt only counts if the fault-injection stack trace
 *       contains FRAME (e.g. "initialize+0x2a/0xe0"); if the fault landed
 *       elsewhere, nearby values of N are probed (fault point numbering can
 *       drift slightly between boots, e.g. during module loading).
 *
 * Output (line based, parsed by the host orchestrator):
 *   @@BEGIN n=<N>                     (flushed before the attempt runs)
 *   @@ATTEMPT n=<N> ret=<rc> errno=<e> injected=<0|1>
 *   K <kernel log message>
 *   @@END
 *   @@MISS n=<N> expect=<FRAME>      (repeat --expect found no match)
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/syscall.h>
#include <unistd.h>

enum mode { MODE_TRIGGER, MODE_INIT };

struct opts {
	const char *cmd;
	enum mode mode;
	const char *target;
	const char *out;
	const char *expect;
	const char *filter;	/* module name: count only faults with it on the stack */
	int random;
	long start;
	long max;
	long nth;
	long count;
	long window;
};

static FILE *out;
static int kmsg_fd = -1;
static int nth_fd = -1;

/* Kernel log of the most recent attempt. */
static char *klog;
static size_t klog_len, klog_cap;

static void die(const char *fmt, ...)
{
	va_list ap;

	va_start(ap, fmt);
	fprintf(stderr, "klg-agent: ");
	vfprintf(stderr, fmt, ap);
	fprintf(stderr, "\n");
	va_end(ap);
	exit(2);
}

/* Write a marker into the kernel log so attempts are easy to find in dmesg. */
static void kmsg_mark(const char *fmt, ...)
{
	char buf[256];
	va_list ap;
	int fd, len;

	va_start(ap, fmt);
	len = vsnprintf(buf, sizeof(buf), fmt, ap);
	va_end(ap);
	fd = open("/dev/kmsg", O_WRONLY);
	if (fd < 0)
		return;
	(void)!write(fd, buf, len); /* marker is best effort */
	close(fd);
}

static void kmsg_open(void)
{
	kmsg_fd = open("/dev/kmsg", O_RDONLY | O_NONBLOCK);
	if (kmsg_fd < 0)
		die("open /dev/kmsg: %s", strerror(errno));
	/* Only records produced from now on are of interest. */
	lseek(kmsg_fd, 0, SEEK_END);
}

static void klog_append(const char *msg)
{
	size_t n = strlen(msg);

	if (klog_len + n + 2 > klog_cap) {
		klog_cap = (klog_len + n + 2) * 2;
		klog = realloc(klog, klog_cap);
		if (!klog)
			die("out of memory");
	}
	memcpy(klog + klog_len, msg, n);
	klog_len += n;
	klog[klog_len++] = '\n';
	klog[klog_len] = '\0';
}

/* Collect every new kernel log record into klog (if keep) or discard it. */
static void kmsg_collect(int keep)
{
	char rec[8192];

	for (;;) {
		ssize_t n = read(kmsg_fd, rec, sizeof(rec) - 1);
		char *msg, *nl;

		if (n < 0) {
			if (errno == EPIPE) /* records overwritten; keep going */
				continue;
			break; /* EAGAIN: no more records */
		}
		if (!keep)
			continue;
		rec[n] = '\0';
		/* Record format: "prio,seq,ts,flags;message\n[ KEY=val\n]..." */
		msg = strchr(rec, ';');
		msg = msg ? msg + 1 : rec;
		nl = strchr(msg, '\n');
		if (nl)
			*nl = '\0';
		klog_append(msg);
	}
}

static void nth_set(long n)
{
	char buf[32];
	int len = snprintf(buf, sizeof(buf), "%ld", n);

	if (pwrite(nth_fd, buf, len, 0) != len)
		die("write fail-nth: %s", strerror(errno));
}

/*
 * Disarm a fault that the target path did not consume. Our own syscalls are
 * fault points too: if the write's copy_from_user is the one that fails
 * (EFAULT), the counter has just reached zero, which is the goal anyway.
 */
static void nth_disarm(void)
{
	if (pwrite(nth_fd, "0", 1, 0) != 1 && errno != EFAULT)
		die("disarm fail-nth: %s", strerror(errno));
}

/*
 * After an attempt: fail-nth reads back 0 iff the armed fault fired during
 * the attempt. If the read itself fails with EFAULT, the pending fault was
 * consumed by our own copy_to_user, which also means it did not fire inside
 * the target path.
 */
static int nth_consumed(void)
{
	char buf[32] = { 0 };
	ssize_t n = pread(nth_fd, buf, sizeof(buf) - 1, 0);

	if (n <= 0)
		return 0;
	if (atol(buf) != 0) {
		nth_disarm();
		return 0;
	}
	return 1;
}

/*
 * Random-injection baseline: opt this task into probabilistic faults
 * (task-filter) only for the duration of the target syscall. Turning it off
 * is itself a syscall that may be failed, so retry until it sticks.
 */
static void random_faults(const struct opts *o, int on)
{
	static int fd = -1;

	if (!o->random)
		return;
	if (fd < 0)
		fd = open("/proc/thread-self/make-it-fail", O_WRONLY);
	if (fd < 0)
		die("open make-it-fail: %s", strerror(errno));
	while (pwrite(fd, on ? "1" : "0", 1, 0) != 1)
		;
}

/*
 * Stack-filtered fault injection. With CONFIG_FAULT_INJECTION_STACKTRACE_FILTER
 * a fault point only counts towards fail-nth if an address in
 * [require-start, require-end) is on its call stack. Setting the range to the
 * target module's code makes the sweep visit only the module's own fault
 * points instead of, e.g., the hundreds inside the kernel's module loader.
 * The module's layout comes from the KLG-MOD lines that klg_modwatch logs.
 */
static const char *const fault_attrs[] = { "failslab", "fail_usercopy", "fail_function" };
static unsigned long filt_lo, filt_hi;

static void write_attr(const char *attr, const char *file, unsigned long v)
{
	char path[128], buf[32];
	int fd, len;

	snprintf(path, sizeof(path), "/sys/kernel/debug/%s/%s", attr, file);
	fd = open(path, O_WRONLY);
	if (fd < 0)
		die("open %s: %s", path, strerror(errno));
	len = snprintf(buf, sizeof(buf), "0x%lx", v);
	if (write(fd, buf, len) != len)
		die("write %s: %s", path, strerror(errno));
	close(fd);
}

static void set_filter(unsigned long lo, unsigned long hi)
{
	size_t i;

	for (i = 0; i < sizeof(fault_attrs) / sizeof(fault_attrs[0]); i++) {
		write_attr(fault_attrs[i], "require-start", lo);
		write_attr(fault_attrs[i], "require-end", hi);
	}
	filt_lo = lo;
	filt_hi = hi;
}

static void clear_filter(void)
{
	if (filt_lo || filt_hi)
		set_filter(0, ~0UL);
	filt_lo = filt_hi = 0;
}

/* Parse "KLG-MOD <name> text=<b>+<s> init=<b>+<s>" for module name in text. */
static int parse_layout(const char *text, const char *name,
			unsigned long *lo, unsigned long *hi)
{
	const char *p = text;
	int found = 0;
	char tag[96];

	snprintf(tag, sizeof(tag), "KLG-MOD %s ", name);
	while ((p = strstr(p, tag))) {
		unsigned long tb, ts, ib, is;

		if (sscanf(p + strlen(tag), "text=%lx+%lx init=%lx+%lx", &tb, &ts, &ib, &is) == 4) {
			*lo = tb;
			*hi = tb + ts;
			if (ib && is) {
				if (ib < *lo)
					*lo = ib;
				if (ib + is > *hi)
					*hi = ib + is;
			}
			found = 1;	/* keep scanning: the last layout wins */
		}
		p += strlen(tag);
	}
	return found;
}

/* Layout of an already loaded module: search the whole kernel log. */
static int layout_from_log(const char *name, unsigned long *lo, unsigned long *hi)
{
	char rec[8192];
	char *all = NULL;
	size_t len = 0;
	int fd = open("/dev/kmsg", O_RDONLY | O_NONBLOCK), found;

	if (fd < 0)
		return 0;
	for (;;) {
		ssize_t n = read(fd, rec, sizeof(rec) - 1);

		if (n < 0) {
			if (errno == EPIPE)
				continue;
			break;
		}
		rec[n] = '\0';
		if (!strstr(rec, "KLG-MOD"))
			continue;
		all = realloc(all, len + n + 1);
		if (!all)
			die("out of memory");
		memcpy(all + len, rec, n);
		len += n;
		all[len] = '\0';
	}
	close(fd);
	found = all ? parse_layout(all, name, lo, hi) : 0;
	free(all);
	return found;
}

static void module_name_from_path(const char *path, char *name, size_t len)
{
	const char *base = strrchr(path, '/');
	size_t i;

	base = base ? base + 1 : path;
	snprintf(name, len, "%s", base);
	for (i = 0; name[i]; i++) {
		if (name[i] == '-')
			name[i] = '_';
		if (!strcmp(name + i, ".ko")) {
			name[i] = '\0';
			break;
		}
	}
}

/* Run the target path once with fail-nth = n. Returns 1 if the fault fired. */
static int attempt(const struct opts *o, long n)
{
	int fd, injected = 0, saved_errno = 0;
	long rc = -1;

	/* Written (and flushed to the host share) before the attempt: if the
	 * kernel crashes or hangs during it, the host knows which fault did it. */
	fprintf(out, "@@BEGIN n=%ld\n", n);
	fflush(out);
	kmsg_mark("KLG: attempt n=%ld target=%s\n", n, o->target);
	kmsg_collect(0); /* discard the marker and anything older */
	klog_len = 0;
	if (klog)
		klog[0] = '\0';

	fd = open(o->target, o->mode == MODE_TRIGGER ? O_WRONLY : O_RDONLY | O_CLOEXEC);
	if (fd < 0) {
		saved_errno = errno;
	} else if (o->mode == MODE_TRIGGER) {
		if (n)
			nth_set(n);
		random_faults(o, 1);
		rc = write(fd, "1", 1);
		if (rc < 0)
			saved_errno = errno;
		random_faults(o, 0);
		injected = n ? nth_consumed() : 0;
		close(fd);
	} else {
		char name[256];

		module_name_from_path(o->target, name, sizeof(name));
		if (n)
			nth_set(n);
		random_faults(o, 1);
		rc = syscall(SYS_finit_module, fd, "", 0);
		if (rc < 0)
			saved_errno = errno;
		random_faults(o, 0);
		injected = n ? nth_consumed() : 0;
		close(fd);
		/* A successful init leaves the module loaded: unload for the next run. */
		if (rc == 0 && syscall(SYS_delete_module, name, O_NONBLOCK) != 0)
			fprintf(stderr, "klg-agent: rmmod %s: %s\n", name, strerror(errno));
	}

	kmsg_collect(1);
	fprintf(out, "@@ATTEMPT n=%ld ret=%ld errno=%d injected=%d\n",
		n, rc, saved_errno, injected);
	if (klog_len) {
		char *line = klog, *nl;

		while ((nl = strchr(line, '\n'))) {
			*nl = '\0';
			fprintf(out, "K %s\n", line);
			*nl = '\n';
			line = nl + 1;
		}
	}
	fprintf(out, "@@END\n");
	fflush(out);
	return injected;
}

/* Restrict fail-nth to the target module's own fault points (--filter). */
static void setup_filter(const struct opts *o)
{
	unsigned long lo, hi;

	if (!o->filter)
		return;
	if (o->mode == MODE_INIT) {
		attempt(o, 0);			/* plain load: klg_modwatch logs the layout */
		if (!parse_layout(klog ? klog : "", o->filter, &lo, &hi))
			die("no KLG-MOD line for %s (is klg_modwatch loaded?)", o->filter);
	} else if (!layout_from_log(o->filter, &lo, &hi)) {
		die("no KLG-MOD line for %s in the kernel log", o->filter);
	}
	set_filter(lo, hi);
	atexit(clear_filter);
}

/*
 * After an init-mode attempt: if the module was loaded at a different address
 * than the filter assumes, move the filter. Returns 1 if the attempt must be
 * repeated because its fault point numbering used the stale range.
 */
static int filter_moved(const struct opts *o)
{
	unsigned long lo, hi;

	if (!o->filter || o->mode != MODE_INIT || !klog)
		return 0;
	if (!parse_layout(klog, o->filter, &lo, &hi) || (lo == filt_lo && hi == filt_hi))
		return 0;
	set_filter(lo, hi);
	return 1;
}

static void sweep(const struct opts *o)
{
	long n = o->start > 0 ? o->start : 1;
	int retries = 0;

	setup_filter(o);
	while (n <= o->max) {
		int injected = attempt(o, n);

		if (filter_moved(o) && ++retries <= 5)
			continue;		/* same n again with the corrected range */
		retries = 0;
		if (!injected)
			break;			/* every fault point of the path visited */
		n++;
	}
}

/* Did the last attempt inject its fault at the expected stack frame? */
static int hit_expected(const char *expect)
{
	const char *fi = klog ? strstr(klog, "FAULT_INJECTION: forcing a failure") : NULL;

	return fi && strstr(fi, expect);
}

static void repeat(const struct opts *o)
{
	long cur = o->nth, k, d;
	int moves = 0;			/* bound re-runs caused by a moving layout */

	if (cur > 0)
		setup_filter(o);
	for (k = 0; k < o->count; k++) {
		int found = 0;

		if (!o->expect || cur == 0) {
			attempt(o, cur);
			if (filter_moved(o) && ++moves <= 10)
				k--;		/* numbering was off: this one does not count */
			continue;
		}
		for (d = 0; d <= o->window && !found; d++) {
			long cand[2] = { cur + d, cur - d };
			int j;

			for (j = 0; j < (d ? 2 : 1) && !found; j++) {
				if (cand[j] < 1)
					continue;
				if (attempt(o, cand[j]) && hit_expected(o->expect)) {
					cur = cand[j];
					found = 1;
				} else if (filter_moved(o) && ++moves <= 10) {
					j--;	/* retry the same candidate with the right range */
				}
			}
		}
		if (!found) {
			fprintf(out, "@@MISS n=%ld expect=%s\n", cur, o->expect);
			fflush(out);
			return;
		}
	}
}

static void usage(void)
{
	fprintf(stderr,
		"usage: klg-agent sweep  --mode trigger|init --target PATH [--max N] [--start N]\n"
		"                        [--filter MODULE] [--out FILE]\n"
		"       klg-agent repeat --mode trigger|init --target PATH --nth N --count R\n"
		"                        [--expect FRAME [--window W]] [--filter MODULE]\n"
		"                        [--random] [--out FILE]\n");
	exit(2);
}

static void parse(int argc, char **argv, struct opts *o)
{
	int i;

	memset(o, 0, sizeof(*o));
	o->max = 500;
	o->count = 1;
	o->nth = -1;
	o->window = 8;
	if (argc < 2)
		usage();
	o->cmd = argv[1];
	for (i = 2; i < argc; i++) {
		const char *a = argv[i], *v = i + 1 < argc ? argv[i + 1] : NULL;

		if (!strcmp(a, "--random")) {
			o->random = 1;
			continue;
		}
		if (!v)
			usage();
		if (!strcmp(a, "--mode"))
			o->mode = !strcmp(v, "init") ? MODE_INIT : MODE_TRIGGER;
		else if (!strcmp(a, "--target"))
			o->target = v;
		else if (!strcmp(a, "--out"))
			o->out = v;
		else if (!strcmp(a, "--expect"))
			o->expect = v;
		else if (!strcmp(a, "--filter"))
			o->filter = v;
		else if (!strcmp(a, "--start"))
			o->start = atol(v);
		else if (!strcmp(a, "--max"))
			o->max = atol(v);
		else if (!strcmp(a, "--nth"))
			o->nth = atol(v);
		else if (!strcmp(a, "--count"))
			o->count = atol(v);
		else if (!strcmp(a, "--window"))
			o->window = atol(v);
		else
			usage();
		i++;
	}
	if (!o->target)
		usage();
}

int main(int argc, char **argv)
{
	struct opts o;

	parse(argc, argv, &o);
	out = o.out ? fopen(o.out, "a") : stdout;
	if (!out)
		die("open %s: %s", o.out, strerror(errno));

	nth_fd = open("/proc/thread-self/fail-nth", O_RDWR);
	if (nth_fd < 0)
		die("open fail-nth (CONFIG_FAULT_INJECTION missing?): %s", strerror(errno));
	kmsg_open();

	if (!strcmp(o.cmd, "sweep")) {
		sweep(&o);
	} else if (!strcmp(o.cmd, "repeat")) {
		if (o.nth < 0)
			usage();
		repeat(&o);
	} else {
		usage();
	}

	if (out != stdout)
		fclose(out);
	return 0;
}
