(function () {
  const page = window.JudgePage || (window.JudgePage = {});

  function getScopeApi() {
    return page.startProtocolScope;
  }

  function getStateApi() {
    return page.startProtocolState;
  }

  function isPendingProtocolEntry(entry) {
    if (!entry) return false;
    return ['WAITING', 'PLANNED', 'STARTING'].includes(String(entry.status || 'WAITING'));
  }

  function hasProtocolPlan(catId) {
    if (!catId) return false;
    const categoryId = String(catId);
    if (
      page.state.spEntries.some(function (entry) {
        return String(entry.category_id) === categoryId;
      })
    ) {
      return true;
    }
    return Object.values(page.state.spStates).some(function (state) {
      return !!(
        state &&
        Array.isArray(state.categoryIds) &&
        state.categoryIds.includes(categoryId) &&
        Array.isArray(state.planned) &&
        state.planned.length > 0
      );
    });
  }

  function getAvailableRiders() {
    const target = getScopeApi().getTarget();
    if (!target.categoryIds.length) return [];
    const inList = new Set(
      page.state.spEntries.map(function (entry) {
        return entry.rider_id;
      })
    );
    return page.state.riders.filter(function (rider) {
      if (inList.has(rider.id)) return false;
      if (!target.categoryIds.includes(String(rider.category_id))) return false;
      if (getScopeApi().isLockedByMassStart(rider.category_id)) return false;
      return true;
    });
  }

  function hasPendingEntries(keyOrCategoryIds) {
    const categoryIds = Array.isArray(keyOrCategoryIds)
      ? keyOrCategoryIds.map(String)
      : keyOrCategoryIds
        ? [String(keyOrCategoryIds)]
        : [];
    const key = Array.isArray(keyOrCategoryIds)
      ? getScopeApi().getTargetKey(categoryIds)
      : String(keyOrCategoryIds || '');
    const state = key ? getStateApi().getState(key) : null;
    return !!(
      key &&
      ((state &&
        Array.isArray(state.planned) &&
        state.planned.some(function (entry) {
          return isPendingProtocolEntry(entry);
        })) ||
        ((!state || !Array.isArray(state.planned)) &&
          page.state.spEntries.some(function (entry) {
            const categoryMatches =
              !categoryIds.length || categoryIds.includes(String(entry.category_id));
            return categoryMatches && isPendingProtocolEntry(entry);
          })))
    );
  }

  function computePausedDelayMs(keyOrCategoryIds) {
    const key = Array.isArray(keyOrCategoryIds)
      ? getScopeApi().getTargetKey(keyOrCategoryIds)
      : String(keyOrCategoryIds || '');
    const state = key ? getStateApi().getState(key) : null;
    if (!state || !state.running || !Array.isArray(state.planned)) return 0;
    const next = state.planned.find(function (entry) {
      return isPendingProtocolEntry(entry) && !state.startedSet.has(entry.rider_id);
    });
    if (!next || next.planned_time === null || next.planned_time === undefined) return 0;
    return Math.max(0, next.planned_time - Date.now());
  }

  function getNextQueueEntry(target) {
    const state = target.key ? getStateApi().getState(target.key, target.categoryIds) : null;
    const startedSet = state ? state.startedSet : new Set();
    return page.state.spEntries.find(function (entry) {
      return isPendingProtocolEntry(entry) && !startedSet.has(entry.rider_id);
    });
  }

  page.startProtocolHasProtocolPlan = hasProtocolPlan;
  page.startProtocolQueue = {
    isPendingProtocolEntry: isPendingProtocolEntry,
    hasProtocolPlan: hasProtocolPlan,
    getAvailableRiders: getAvailableRiders,
    hasPendingEntries: hasPendingEntries,
    computePausedDelayMs: computePausedDelayMs,
    getNextQueueEntry: getNextQueueEntry,
  };
})();
