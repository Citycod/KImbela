#!/bin/bash
# Pre-migration verification checklist — Kimbela push notifications
# Run this BEFORE `flask db upgrade` on production.
# Stop and fix if any step fails or shows unexpected output.

set -e

echo "=================================================="
echo "1. Confirm you're in the Kimbela repo root"
echo "=================================================="
pwd
ls models.py utils/push_service.py users/user.py templates/base.html static/pwa_init.js 2>&1

echo ""
echo "=================================================="
echo "2. Check for uncommitted changes / see the real diff"
echo "=================================================="
echo "--- git status ---"
git status
echo ""
echo "--- git diff on push_service.py (verify 404/410 handling is real, not just pasted) ---"
git diff utils/push_service.py || echo "No unstaged diff — check 'git log -p -1 -- utils/push_service.py' if already committed"

echo ""
echo "=================================================="
echo "3. Search for leftover /api/push/ references"
echo "   (spec assumed /api/push/, actual code uses /api/pwa/)"
echo "=================================================="
grep -rn "api/push" --include="*.py" --include="*.js" --include="*.html" . || echo "None found — clean."

echo ""
echo "=================================================="
echo "4. Confirm both subscribe AND unsubscribe use the same prefix"
echo "=================================================="
grep -rn "api/pwa" --include="*.py" --include="*.js" .

echo ""
echo "=================================================="
echo "5. Check for duplicate endpoints in the DB"
echo "   (this WILL fail the migration if duplicates exist)"
echo "=================================================="
echo "Run this manually against production DB (Neon console or allowlisted connection):"
echo ""
cat <<'SQL'
SELECT endpoint, COUNT(*) 
FROM push_subscriptions 
GROUP BY endpoint 
HAVING COUNT(*) > 1;
SQL
echo ""
echo "If rows are returned, run this to keep the MOST RECENTLY ACTIVE row per endpoint:"
echo ""
cat <<'SQL'
DELETE FROM push_subscriptions a
USING push_subscriptions b
WHERE a.endpoint = b.endpoint
  AND a.last_seen_at < b.last_seen_at;
SQL

echo ""
echo "=================================================="
echo "6. Review the actual migration file before applying"
echo "=================================================="
find migrations/versions -name "*add_push_subscription_columns*" -exec cat {} \;

echo ""
echo "=================================================="
echo "7. Once 1-6 are clean, apply the migration"
echo "=================================================="
echo "cd /var/www/Kimbela"
echo "source my_env/bin/activate   # or venv/bin/activate — confirm which one is real on the VPS"
echo "flask db upgrade"
echo ""
echo "=================================================="
echo "8. Restart the app"
echo "=================================================="
echo "Confirm your actual restart command (systemctl restart <service> / supervisorctl restart / pm2 restart, etc.)"

echo ""
echo "=================================================="
echo "9. Post-deploy smoke test"
echo "=================================================="
echo "- Load the site, open devtools console, confirm no errors on page load (no auto-prompt)"
echo "- Click the Enable Notifications trigger, confirm browser permission prompt appears"
echo "- Accept, confirm POST to /api/pwa/subscribe returns 200 (check network tab)"
echo "- Send a test message from a second account, confirm push notification appears"
echo "- Revoke notification permission in browser settings, send another test message,"
echo "  confirm the dead subscription row is deleted from push_subscriptions (not just silently fails)"
