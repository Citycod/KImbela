(function () {
  'use strict';

  if (window.KimbelaPassivePolling) return;

  const userScope = String(window.currentUserId || 'anonymous');
  const keyPrefix = `kimbela:passive:${userScope}:`;
  const leaseKey = `${keyPrefix}leader`;
  const statePrefix = `${keyPrefix}state:`;
  const claimPrefix = `${keyPrefix}claim:`;
  const channelName = `${keyPrefix}channel`;
  const leaseMs = 45000;
  const heartbeatMs = 15000;
  const sharedStateMaxAgeMs = 2 * 60 * 60 * 1000;
  const tabId = window.crypto && typeof window.crypto.randomUUID === 'function'
    ? window.crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;

  const leadershipListeners = new Set();
  const topicListeners = new Map();
  let channel = null;
  let coordinationTimer = null;
  let started = false;
  let leader = false;

  function isVisible() {
    return document.visibilityState !== 'hidden' && document.hidden !== true;
  }

  function safeParse(value) {
    try {
      return value ? JSON.parse(value) : null;
    } catch (error) {
      return null;
    }
  }

  function storageGet(key) {
    try {
      return window.localStorage.getItem(key);
    } catch (error) {
      return null;
    }
  }

  function storageSet(key, value) {
    try {
      window.localStorage.setItem(key, value);
      return true;
    } catch (error) {
      return false;
    }
  }

  function storageRemove(key) {
    try {
      window.localStorage.removeItem(key);
    } catch (error) {
    }
  }

  function notifyLeadership() {
    leadershipListeners.forEach(listener => {
      try {
        listener(leader && isVisible());
      } catch (error) {
      }
    });
  }

  function setLeader(nextLeader) {
    const changed = leader !== nextLeader;
    leader = nextLeader;
    if (changed) notifyLeadership();
  }

  function currentLease() {
    return safeParse(storageGet(leaseKey));
  }

  function renewOrAcquireLease() {
    if (!isVisible()) {
      releaseLease();
      return false;
    }

    const now = Date.now();
    const lease = currentLease();
    if (lease && lease.tabId !== tabId && Number(lease.expiresAt) > now) {
      setLeader(false);
      return false;
    }

    const candidate = JSON.stringify({ tabId, expiresAt: now + leaseMs });
    if (!storageSet(leaseKey, candidate)) {
      // Private-storage failures fall back to this visible tab without polling loops.
      setLeader(true);
      return true;
    }

    const confirmed = currentLease();
    const acquired = Boolean(confirmed && confirmed.tabId === tabId);
    setLeader(acquired);
    if (acquired && channel) {
      channel.postMessage({ type: 'lease', tabId });
    }
    return acquired;
  }

  function releaseLease() {
    const lease = currentLease();
    if (lease && lease.tabId === tabId) {
      storageRemove(leaseKey);
      if (channel) channel.postMessage({ type: 'lease-released', tabId });
    }
    setLeader(false);
  }

  function startCoordinationTimer() {
    if (coordinationTimer || !isVisible()) return;
    coordinationTimer = window.setInterval(renewOrAcquireLease, heartbeatMs);
  }

  function stopCoordinationTimer() {
    if (!coordinationTimer) return;
    window.clearInterval(coordinationTimer);
    coordinationTimer = null;
  }

  function handleVisibilityChange() {
    if (isVisible()) {
      renewOrAcquireLease();
      startCoordinationTimer();
    } else {
      stopCoordinationTimer();
      releaseLease();
    }
  }

  function emitTopic(topic, payload) {
    const listeners = topicListeners.get(topic);
    if (!listeners) return;
    listeners.forEach(listener => {
      try {
        listener(payload);
      } catch (error) {
      }
    });
  }

  function handleChannelMessage(event) {
    const message = event && event.data;
    if (!message) return;
    if (message.type === 'state') {
      emitTopic(message.topic, message.payload);
      return;
    }
    if (message.type === 'lease-released' || message.type === 'lease') {
      renewOrAcquireLease();
    }
  }

  function handleStorage(event) {
    if (!event || event.key === leaseKey) {
      renewOrAcquireLease();
      return;
    }
    if (event.key && event.key.startsWith(statePrefix) && event.newValue) {
      const record = safeParse(event.newValue);
      if (record) emitTopic(event.key.slice(statePrefix.length), record.payload);
    }
  }

  function start() {
    if (started) return;
    started = true;
    if ('BroadcastChannel' in window) {
      try {
        channel = new window.BroadcastChannel(channelName);
        channel.addEventListener('message', handleChannelMessage);
      } catch (error) {
        channel = null;
      }
    }
    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('storage', handleStorage);
    window.addEventListener('pagehide', releaseLease);
    window.addEventListener('beforeunload', releaseLease);
    handleVisibilityChange();
  }

  function publish(topic, payload) {
    const record = { payload, publishedAt: Date.now(), tabId };
    storageSet(`${statePrefix}${topic}`, JSON.stringify(record));
    if (channel) channel.postMessage({ type: 'state', topic, payload });
  }

  function subscribe(topic, listener) {
    start();
    if (!topicListeners.has(topic)) topicListeners.set(topic, new Set());
    topicListeners.get(topic).add(listener);
    const record = safeParse(storageGet(`${statePrefix}${topic}`));
    if (record && Date.now() - Number(record.publishedAt) <= sharedStateMaxAgeMs) {
      listener(record.payload);
    }
    return function unsubscribe() {
      topicListeners.get(topic)?.delete(listener);
    };
  }

  function onLeadershipChange(listener) {
    start();
    leadershipListeners.add(listener);
    listener(leader && isVisible());
    return function unsubscribe() {
      leadershipListeners.delete(listener);
    };
  }

  function claimOnce(name, ttlMs) {
    start();
    if (!isVisible()) return false;
    const key = `${claimPrefix}${name}`;
    const now = Date.now();
    const existing = safeParse(storageGet(key));
    if (existing && now - Number(existing.claimedAt) < ttlMs) return false;

    const claim = { tabId, claimedAt: now };
    if (!storageSet(key, JSON.stringify(claim))) return true;
    const confirmed = safeParse(storageGet(key));
    return Boolean(
      confirmed
      && confirmed.tabId === tabId
      && Number(confirmed.claimedAt) === now
    );
  }

  function destroy() {
    stopCoordinationTimer();
    releaseLease();
    document.removeEventListener('visibilitychange', handleVisibilityChange);
    window.removeEventListener('storage', handleStorage);
    window.removeEventListener('pagehide', releaseLease);
    window.removeEventListener('beforeunload', releaseLease);
    if (channel) channel.close();
    channel = null;
    started = false;
  }

  window.KimbelaPassivePolling = {
    isLeader() {
      start();
      return leader && isVisible();
    },
    isVisible,
    onLeadershipChange,
    publish,
    subscribe,
    claimOnce,
    destroy,
  };
})();
