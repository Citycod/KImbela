---
name: PWA Push Notifications for New Messages
description: >
  Implementation guide for adding PWA web push notifications to Kimbela,
  triggered only on new direct messages. Covers database model, backend
  routes, pywebpush integration, service worker, client-side subscribe
  flow, and testing checklist. Scoped to Kimbela's Flask/SQLAlchemy stack.
---

# Task: Implement PWA Push Notifications for New Messages — Kimbela

## Context
Kimbela is a Flask-based social platform hosted on a Contabo Ubuntu VPS at `/var/www/Kimbela/`. We're adding PWA push notifications, scoped to a single trigger: **new direct messages only**. VAPID keys are already generated and present in the server `.env`. Do not touch unrelated features. Do not introduce new dependencies beyond what's listed below without flagging it first.

## Stack constraints
- Backend: Flask (existing app structure — inspect `/var/www/Kimbela/` before creating new files, match existing patterns for blueprints/models/db session handling)
- Push library: `pywebpush` (Python)
- Queue: none for MVP — synchronous send is acceptable at current volume, but must be wrapped so a failed push never breaks the message-send request
- DB: match whatever Kimbela already uses (inspect models directory first — likely SQLAlchemy)
- No new frontend framework — vanilla JS service worker, no build step

## Part 1 — Database
Create a `push_subscriptions` table/model with these columns:
- `id` (PK)
- `user_id` (FK to existing users table)
- `endpoint` (string, unique, not null)
- `p256dh_key` (string, not null)
- `auth_key` (string, not null)
- `user_agent` (string, nullable — for debugging)
- `created_at` (timestamp, default now)
- `last_seen_at` (timestamp, default now, updated on each successful send)

Important: a user can have **multiple** subscriptions (multiple devices/browsers). Do not design this as one-subscription-per-user. Uniqueness constraint is on `endpoint`, not `user_id`.

Write the migration consistent with however Kimbela currently handles migrations (check for Flask-Migrate/Alembic in the repo first).

## Part 2 — Backend routes
Add these endpoints (match existing Kimbela route/blueprint conventions and auth decorators):

1. `POST /api/push/subscribe`
   - Accepts the browser's `PushSubscription` JSON (`endpoint`, `keys.p256dh`, `keys.auth`)
   - Requires authenticated user (use existing session/login-required pattern)
   - Upsert: if `endpoint` already exists, update `user_id`/`last_seen_at` instead of erroring on duplicate
   - Store `user_agent` from request headers

2. `POST /api/push/unsubscribe`
   - Accepts `endpoint`
   - Deletes the matching row for the current user

3. Internal helper function `send_push_to_user(user_id, payload: dict)` (not a route — called from message-creation logic):
   - Fetch all `push_subscriptions` rows for `user_id`
   - For each, call `pywebpush` with the stored keys and VAPID credentials from `.env`
   - **Critical**: wrap each send in try/except. On `WebPushException` with `response.status_code` in `(404, 410)`, delete that subscription row (it's dead — browser revoked it). On other exceptions, log and continue to the next subscription — never let one failed subscription block others or bubble up to the caller.
   - This function must be safe to call synchronously inside the existing "create message" request handler without ever causing that handler to 500. Wrap the whole call site in try/except as a second layer of defense.

## Part 3 — Trigger point
Find the existing message-creation logic (likely in a messages/chat blueprint or model). After a message is successfully saved to the DB, call:

```python
send_push_to_user(
    user_id=recipient_id,
    payload={
        "title": sender.display_name,
        "body": message.content[:120],  # truncate for preview
        "icon": "/static/icons/icon-192.png",  # confirm actual path in repo
        "data": {"url": f"/messages/{conversation_id}"}  # deep link
    }
)
```

Do **not** send a push if the recipient is currently active in that same conversation (check however Kimbela currently tracks online/active-conversation state — if there's no such tracking yet, skip this optimization for MVP and just always send).

## Part 4 — Service worker
Create/update `static/sw.js` (confirm existing SW file path/registration first — Kimbela may already have one for PWA caching; extend it, don't replace it):

```js
self.addEventListener('push', function(event) {
  const data = event.data ? event.data.json() : {};
  const title = data.title || 'Kimbela';
  const options = {
    body: data.body || '',
    icon: data.icon || '/static/icons/icon-192.png',
    badge: '/static/icons/badge-72.png',
    data: data.data || {},
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', function(event) {
  event.notification.close();
  const url = event.notification.data?.url || '/';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clientList => {
      for (const client of clientList) {
        if (client.url.includes(url) && 'focus' in client) return client.focus();
      }
      if (clients.openWindow) return clients.openWindow(url);
    })
  );
});
```

## Part 5 — Client-side subscribe flow
Add a JS module (fits into existing frontend structure — check if Kimbela has a shared `app.js` or similar) that:

1. Checks `'serviceWorker' in navigator && 'PushManager' in window` before doing anything (graceful no-op on unsupported browsers, e.g. iOS Safari outside of "Add to Home Screen" context — flag this limitation to the user in the UI, don't fail silently with no explanation)
2. Registers the service worker if not already registered
3. On a user-initiated action (a settings toggle or "Enable notifications" button — **not** on page load, browsers penalize/auto-deny unprompted permission requests), calls `Notification.requestPermission()`
4. If granted, subscribes via `pushManager.subscribe()` using the VAPID public key (expose this to frontend via a template variable or a small `/api/push/vapid-public-key` endpoint — do not hardcode it in JS)
5. POSTs the subscription object to `/api/push/subscribe`
6. Handle the "already subscribed" case gracefully (browser returns existing subscription if one exists — just re-POST it, backend upsert handles the rest)

## Part 6 — Config
Confirm these exist in `.env` (per prior context they're already added):
- `VAPID_PUBLIC_KEY`
- `VAPID_PRIVATE_KEY`
- `VAPID_CLAIM_EMAIL` (mailto: address for the `sub` claim)

Load these via whatever config pattern Kimbela already uses (`os.environ` / `python-dotenv` / config class — inspect first).

## Non-goals for this pass (do not build)
- No notification preferences/settings beyond on/off (no per-conversation muting)
- No queue/worker infrastructure — synchronous send only
- No notification grouping/batching
- No Android/iOS native push (Firebase Cloud Messaging) — web push only
- No read-receipt or delivery-confirmation tracking

## Testing checklist to verify before calling this done
- [ ] Subscribe flow works on Chrome desktop and Chrome Android
- [ ] Duplicate subscribe (same browser, re-triggering) doesn't create duplicate rows
- [ ] Sending a message to a user with 2 active subscriptions (e.g. desktop + mobile) delivers to both
- [ ] Killing a subscription (revoke notification permission in browser settings) and then triggering a send results in that row being deleted from `push_subscriptions`, not an unhandled error
- [ ] A failed push to one dead subscription doesn't prevent delivery to the user's other valid subscriptions
- [ ] Message send request still returns 200 and completes normally even if push sending fails entirely
- [ ] Notification click opens/focuses the correct conversation

## Deliverable
List every file created or modified, with a one-line description of the change per file.
