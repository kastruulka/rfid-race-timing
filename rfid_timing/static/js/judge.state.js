(function () {
  const page = window.JudgePage || (window.JudgePage = {});

  page.toast = window.showToast;
  page.constants = {
    LOG_POLL_MS: 5000,
    RACE_STATUS_POLL_MS: 500,
    RIDER_PANEL_POLL_MS: 700,
    TIMER_TICK_MS: 100,
    COUNTDOWN_TICK_MS: 100,
    START_PROTOCOL_INTERVAL_SEC: 30,
    START_PROTOCOL_STALE_MS: 10 * 60 * 1000,
  };
  page.messages = {
    authRequired: 'Для выполнения действия судьи требуется войти в систему',
    selectCategory: 'Выберите категорию',
    selectProtocolCategory: 'Сначала выберите категорию',
    selectRider: 'Выберите участника',
  };

  page.state = {
    riders: [],
    selectedRiderId: null,
    startMode: 'mass',
    spStates: {},
    spEntries: [],
    spCountdownTimer: null,
    spDragIdx: null,
    spDropdown: null,
    riderDropdown: null,
    catTimerElapsed: {},
    catTimerPerf: {},
    catTimerClosed: {},
    globalTimerRef: null,
    authManager: null,
    http: null,
    currentCategoryStarted: false,
    currentCategoryClosed: false,
    raceStatusRequestInFlight: false,
    raceStatusReloadRequested: false,
    riderPanelRequestInFlight: false,
    lastLapsHash: '',
    pollingRefs: { log: null, race: null, riderPanel: null },
  };
  page.categoryNames = {};

  page.getResponseData = function getResponseData(result) {
    if (!result || result.unauthorized) return null;
    return result.data === undefined ? result : result.data;
  };

  page.isResponseOk = function isResponseOk(result) {
    const data = page.getResponseData(result);
    return !!(result && result.ok && (!data || data.ok !== false));
  };

  page.getResponseError = function getResponseError(result, fallback) {
    const data = page.getResponseData(result);
    return (data && data.error) || fallback || 'Ошибка';
  };

  page.requireRider = function requireRider() {
    if (!page.state.selectedRiderId) {
      page.toast(page.messages.selectRider, true);
      return false;
    }
    return true;
  };

  page.requireJudgeEditAccess = function requireJudgeEditAccess(message) {
    if (!page.state.authManager || page.state.authManager.state.authenticated) return true;
    page.state.authManager.login({ reason: message || page.messages.authRequired, silent: true });
    return false;
  };

  page.ensureJudgeAuth = async function ensureJudgeAuth(message) {
    if (page.state.authManager && page.state.authManager.state.authenticated) return true;
    await page.state.authManager.login({
      reason: message || page.messages.authRequired,
      silent: true,
    });
    return false;
  };

  function setRiders(data) {
    page.state.riders = Array.isArray(data) ? data : [];
  }

  function applyCategoryList(data) {
    const categories = Array.isArray(data) ? data : [];
    page.categoryNames = {};
    categories.forEach(function (cat) {
      page.categoryNames[String(cat.id)] = cat.name;
    });
    return categories;
  }

  function applyRaceState(data, catId, now) {
    const safeData = data || {};
    const catStates = safeData.category_states || {};
    const nextLifecycleById = {};
    const perfNow = now === undefined ? performance.now() : now;

    if (Array.isArray(safeData.categories)) {
      safeData.categories.forEach(function (cat) {
        page.categoryNames[String(cat.id)] = cat.name;
      });
    }

    Object.keys(page.state.catTimerElapsed).forEach(function (cid) {
      if (!(cid in catStates)) {
        delete page.state.catTimerElapsed[cid];
        delete page.state.catTimerPerf[cid];
        delete page.state.catTimerClosed[cid];
      }
    });

    Object.entries(catStates).forEach(function (item) {
      const cid = item[0];
      const entry = item[1] || {};
      nextLifecycleById[cid] = {
        started: !!entry.started_at,
        closed: entry.closed === true,
      };
      if (entry.elapsed_ms !== null && entry.elapsed_ms !== undefined) {
        page.state.catTimerElapsed[cid] = entry.elapsed_ms;
        page.state.catTimerPerf[cid] = perfNow;
        page.state.catTimerClosed[cid] = entry.closed === true;
      }
    });

    if (catId) {
      nextLifecycleById[String(catId)] = {
        started: safeData.category_started === true,
        closed: safeData.category_closed === true,
      };
    }

    page.replaceCategoryLifecycleState(nextLifecycleById);

    return {
      status: safeData.status || {},
      lifecycle: page.syncCurrentCategoryLifecycle(catId),
      categoryStates: catStates,
    };
  }

  page.stateStore = {
    setRiders: setRiders,
    applyCategoryList: applyCategoryList,
    applyRaceState: applyRaceState,
  };
})();
