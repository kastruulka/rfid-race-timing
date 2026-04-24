(function () {
  const page = window.JudgePage || (window.JudgePage = {});

  function getTargetKey(categoryIds) {
    if (page.startProtocolScope && typeof page.startProtocolScope.getTargetKey === 'function') {
      return page.startProtocolScope.getTargetKey(categoryIds);
    }
    const ids = (categoryIds || []).map(String).filter(Boolean);
    if (!ids.length) return '';
    return ids.length === 1 ? ids[0] : 'multi:' + ids.join(',');
  }

  function getState(key, categoryIds) {
    if (!key) return null;
    if (!page.state.spStates[key]) {
      page.state.spStates[key] = {
        planned: null,
        running: false,
        startedSet: new Set(),
        pausedDelayMs: null,
        categoryIds: (categoryIds || []).map(String),
        statusSyncInFlight: false,
        lastOverdueSyncAt: 0,
      };
    }
    if (Array.isArray(categoryIds) && categoryIds.length) {
      page.state.spStates[key].categoryIds = categoryIds.map(String);
    }
    return page.state.spStates[key];
  }

  function isRunning(keyOrCategoryId) {
    const direct = page.state.spStates[String(keyOrCategoryId || '')];
    if (direct) return !!direct.running;
    const categoryId = String(keyOrCategoryId || '');
    if (!categoryId) return false;
    return Object.values(page.state.spStates).some(function (state) {
      return !!(
        state &&
        state.running &&
        Array.isArray(state.categoryIds) &&
        state.categoryIds.includes(categoryId)
      );
    });
  }

  function saveAllStates() {
    const data = {};
    Object.entries(page.state.spStates).forEach(function (item) {
      const key = item[0];
      const state = item[1];
      if (!state || !Array.isArray(state.planned) || !state.planned.length) return;
      data[key] = {
        planned: state.planned,
        startedRiders: Array.from(state.startedSet || []),
        running: !!state.running,
        pausedDelayMs: state.pausedDelayMs,
        categoryIds: state.categoryIds || [],
      };
    });
    if (Object.keys(data).length) sessionStorage.setItem('sp_states', JSON.stringify(data));
    else sessionStorage.removeItem('sp_states');
  }

  function restoreAllStates() {
    try {
      const raw = sessionStorage.getItem('sp_states');
      if (!raw) return false;
      const data = JSON.parse(raw);
      let restored = false;
      Object.entries(data).forEach(function (item) {
        const key = item[0];
        const saved = item[1];
        if (!saved || !Array.isArray(saved.planned) || !saved.planned.length) return;
        const lastPlanned = saved.planned[saved.planned.length - 1].planned_time;
        if (
          saved.running &&
          lastPlanned &&
          Date.now() - lastPlanned > page.constants.START_PROTOCOL_STALE_MS
        ) {
          return;
        }
        const state = getState(key, saved.categoryIds || []);
        state.planned = saved.planned;
        state.startedSet = new Set(saved.startedRiders || []);
        state.running = !!saved.running;
        state.pausedDelayMs = saved.pausedDelayMs ?? null;
        restored = true;
      });
      if (!restored) sessionStorage.removeItem('sp_states');
      return restored;
    } catch {
      return false;
    }
  }

  function clearStateFor(keyOrCategoryIds) {
    const key = Array.isArray(keyOrCategoryIds)
      ? getTargetKey(keyOrCategoryIds)
      : String(keyOrCategoryIds || '');
    if (!key || !page.state.spStates[key]) return;
    page.state.spStates[key].running = false;
    page.state.spStates[key].planned = null;
    page.state.spStates[key].startedSet = new Set();
    page.state.spStates[key].pausedDelayMs = null;
    saveAllStates();
  }

  function clearStatesForCategory(categoryId) {
    const keyCategoryId = String(categoryId || '');
    if (!keyCategoryId) return;
    Object.entries(page.state.spStates).forEach(function (item) {
      const key = item[0];
      const state = item[1];
      if (!state) return;
      const categoryIds = Array.isArray(state.categoryIds) ? state.categoryIds.map(String) : [];
      if (key === keyCategoryId || categoryIds.includes(keyCategoryId)) {
        clearStateFor(key);
      }
    });
  }

  page.startProtocolState = {
    getState: getState,
    isRunning: isRunning,
    saveAllStates: saveAllStates,
    restoreAllStates: restoreAllStates,
    clearStateFor: clearStateFor,
    clearStatesForCategory: clearStatesForCategory,
  };
})();
