---
trigger: always_on
---

# Antigravity Verification Rules

Add these to the existing Antigravity development rules document. These govern
how Antigravity must behave for anything touching database schema, deployment,
infrastructure, or auth — the categories where "I read the code and assumed"
has caused real production incidents.

---

## 1. Never infer runtime state from source code — verify it live

Code existing in the repo (a model, a route, a config value) is **not**
evidence that the corresponding runtime state exists (a DB table, a running
service, a deployed version, an env var actually set).

Before writing or running any migration, deployment script, or infra change,
Antigravity must verify the *actual current state* with a live check:

- **Database schema**: query `information_schema.tables` /
  `information_schema.columns` (or `\d tablename`) against the real target
  database before writing a migration that alters or assumes an existing
  table. Never assume a table exists because a model class exists in
  `models.py`.
- **Running services/processes**: check `systemctl status`, `ps aux`, or
  equivalent before assuming something is/isn't running, or before creating a
  new service that might duplicate one that already exists.
- **Deployed code version**: check `git log` / `git status` on the actual
  target (VPS, staging) before assuming it matches what's committed locally
  or on `origin/main`.
- **Env vars / secrets**: confirm a variable is actually set in the target
  environment's `.env` — don't assume it's there because it's referenced in
  code.

If Antigravity cannot verify live state directly (blocked connection, no
access), it must say so explicitly and ask the user to verify, rather than
proceeding on an assumption.

## 2. Show diffs and query results, not summaries, for anything high-stakes

For changes touching database schema, authentication, deployment scripts, or
infrastructure config, Antigravity must show the user:
- The actual `git diff` (not a paraphrase of it)
- The actual migration file content
- The actual query result confirming a pre-condition (e.g., "no duplicate
  endpoints" must be a pasted query result, not an assertion)

A written summary of what changed is not sufficient for these categories. If
Antigravity claims "X was already there / already correct," it must show the
literal code, not a reconstructed description of it.

## 3. No confidence claims without a corresponding check

Antigravity must not say things like "completely safe," "no pre-checks
required," or "you're good to deploy" unless that conclusion is backed by an
actual check performed in that session. If the confidence is based on
inference from reading code rather than a live verification, Antigravity must
say so plainly: "I believe X based on the code, but haven't verified it
directly — here's how to check."

## 4. Test migrations against a non-production target first

Before running any migration against the production database, Antigravity
must either:
- Run it against a staging/branch database first (Neon branching is
  available for this — use it), or
- If no staging exists, explicitly flag that this migration has not been
  tested anywhere except production, and list exactly what could go wrong.

Never present a migration as ready to run on production as the first and only
place it will execute, without flagging that explicitly.

## 5. Audit existing infrastructure before adding new infrastructure

Before adding a new service, script, cron job, or background process,
Antigravity must check what's already running that might overlap or
conflict:

```bash
systemctl list-units --type=service
crontab -l
sudo lsof -i -P -n | grep LISTEN
```

If Antigravity creates a new long-running service (systemd unit, background
script, webhook listener, etc.), it must:
- Bind to `127.0.0.1`, not `0.0.0.0`, unless the service genuinely needs to
  be reachable externally
- Never hardcode secrets/tokens directly in the file — use `.env`
- Implement any stated security check (signature validation, auth) for real,
  not as a comment saying it should be added later
- Tell the user explicitly what port it's on and confirm firewall rules
  actually restrict access to it

## 6. Periodic infrastructure audit (independent of feature work)

Recommend running this checklist periodically, not just when investigating a
bug — the webhook incident was found by accident:

```bash
systemctl list-units --type=service
sudo ufw status
sudo lsof -i -P -n | grep LISTEN
crontab -l
```

Anything running that isn't recognized, isn't documented, or isn't
firewalled should be investigated before being left alone.

## 7. Migration rollback safety

Every migration Antigravity writes must have a correct, tested `downgrade()`
function — not a placeholder. Before applying any migration, confirm:
- `flask db current` shows the expected starting revision
- The migration's `down_revision` matches that starting revision exactly
- If the migration fails partway, confirm the DB is left in the pre-migration
  state (Alembic wraps DDL in a transaction by default for Postgres — confirm
  this wasn't overridden)

## 8. When in doubt, ask before running anything against production

If any of the above checks can't be completed (blocked connection, ambiguous
state, conflicting information between what code says and what's observed),
Antigravity should stop and ask the user rather than proceeding with the most
likely interpretation. A pause costs minutes. A bad migration or exposed
service costs hours and trust.