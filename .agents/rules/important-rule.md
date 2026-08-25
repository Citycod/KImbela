---
trigger: always_on
---

/

**KIMBELA — CODEBASE INTEGRITY RULES (addendum to global Antigravity rules)**

**1. No duplicate files, ever.**
Before creating any file, search for an existing one that already owns this responsibility. Specifically for Kimbela:
- Dashboard-related routes → stay in the existing `users/user.py` blueprint. Do not create `dashboard_routes.py`, `user_v2.py`, or similar.
- Templates → edit `templates/user_dashboard.html` and its existing `partials/` includes (`user_dashboard_head_scripts.html`, `user_dashboard_pre_scripts.html`, `user_dashboard_body_scripts.html`, `report_modal.html`) in place. Do not create `user_dashboard_new.html` or a parallel partial that duplicates an existing one's job.
- Static assets → CSS/JS changes go into the existing files under `static/assets/css/` and `static/assets/js/`. Do not add `dashboard2.css`, `main-fixed.js`, etc.

**2. CSS consolidation is additive-then-subtractive, not parallel.**
When merging `main.css`, `dashboard.css`, `user_dashboard_inline.css`, and `dashboard_redesign.css` into one bundle: the four original files must be deleted and all `<link>` references removed from the template in the *same* change that introduces the bundle. A period where both the old files and the new bundle exist in the tree is not acceptable as a "finished" state — only as an intermediate step within one PR/commit.

**3. No orphaned "override" files.**
`dashboard_redesign.css` exists as a comment-labeled override layer patching earlier CSS with `!important`. This pattern is not to be repeated. If new dashboard styling is needed, it goes into the consolidated bundle directly — never as a new override file stacked on top.

**4. Cache-busting must use one mechanism, defined once.**
Whatever versioning approach is chosen (static string, config variable, file hash) must be defined in a single place (e.g. Flask config or a build step) and referenced consistently across every asset tag. Do not mix a hardcoded `?v=1.0.0` on some tags with a different scheme on others.

**5. AI persona logic (Amara, Tunde, Ngozi, Emeka) stays where persona logic already lives.**
Do not scatter persona-related queries or generation calls across multiple new files or inline into the dashboard view "just to fix the slowness." If persona activity needs to move to a background job (Celery/RQ/cron), it goes into a clearly-named, single module for that purpose — and the dashboard route calls into it, rather than duplicating logic inline.

**6. Every performance fix must state what it touched and what it deliberately left alone.**
For each change (cache-busting, CSS consolidation, CDN self-hosting, query timing), Antigravity must report: file(s) changed, what was removed, and confirmation that no other template/route still references the removed thing (old CSS class names, old `<link>` tags, old function calls).

**7. No speculative restructuring during a bug fix.**
This is a performance debugging task, not a rearchitecture. Do not introduce new folder structures, new blueprints, or new abstraction layers (e.g. a "PersonaService" class, a new caching framework) unless the timing data explicitly shows it's needed and you've confirmed that with me first.

**8. Verify with a search before declaring done.**
After any file is renamed, merged, or deleted, grep the full `templates/` and `static/` trees for lingering references before marking the task complete.

