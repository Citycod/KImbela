const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const findSource = fs.readFileSync(
  path.resolve(__dirname, '../../templates/view_requests.html'),
  'utf8',
);
const gateSource = fs.readFileSync(
  path.resolve(__dirname, '../../templates/matchmaking_browse_paywall.html'),
  'utf8',
);

test('unpaid initialization shows the preview gate without loading people', () => {
  assert.match(
    findSource,
    /if \(hasMatchmakingAccess\) \{\s*loadRequests\(\);\s*\} else \{\s*showMatchmakingAccessGate\(false\);/,
  );
  assert.match(
    findSource,
    /async function loadRequests\(\) \{\s*if \(!hasMatchmakingAccess\)/,
  );
  assert.match(findSource, /response\.status === 402/);
  assert.match(gateSource, /Unlock Find Your Match/);
  assert.match(gateSource, /\$\{\{ matchmaking_access_price_usd \}\} USD/);
});

test('Find Matches and See Everyone share one protected result and payment path', () => {
  assert.match(findSource, /id="applyFilters"[\s\S]*?Find Matches/);
  assert.match(findSource, /id="seeEveryoneButton"[\s\S]*?See Everyone/);
  assert.match(findSource, /function seeEveryone\(\) \{\s*clearFilters\(\);\s*\}/);
  assert.equal((findSource.match(/\/api\/browse\/users\?/g) || []).length, 1);
  assert.equal((findSource.match(/start_browse_access_payment/g) || []).length, 1);
  assert.match(gateSource, /Find Your Match and See Everyone included/);
});
