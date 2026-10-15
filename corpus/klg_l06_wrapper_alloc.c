// SPDX-License-Identifier: GPL-2.0
/*
 * L06 - interprocedural: the object comes from an allocation wrapper.
 * session_create() returns fresh memory; the caller leaks it when the
 * token allocation fails.
 */
#include <linux/slab.h>
#include <linux/string.h>
#include "klg_harness.h"

struct session {
	int id;
	char tag[16];
};

static noinline struct session *session_create(int id)
{
	struct session *s;

	s = kzalloc(sizeof(*s), GFP_KERNEL);	/* GT:SAFE */
	if (!s)
		return NULL;
	s->id = id;
	return s;
}

static noinline void session_destroy(struct session *s)
{
	kfree(s);
}

static noinline int session_start(void)
{
	struct session *s;
	char *tok;

	s = session_create(7);			/* GT:LEAK */
	if (!s)
		return -ENOMEM;

	tok = kmalloc(64, GFP_KERNEL);		/* GT:SAFE */
	if (!tok)
		return -ENOMEM;		/* s leaks here */

	strscpy(tok, "token", 64);
	strscpy(s->tag, tok, sizeof(s->tag));
	kfree(tok);
	session_destroy(s);
	return 0;
}

KLG_TRIGGER(session_start);
KLG_SIMPLE_MODULE("KLG L06: leak of an object returned by an allocation wrapper");
