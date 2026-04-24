(function () {
  const page = window.JudgePage || (window.JudgePage = {});

  function getStoredProtocolInterval(key) {
    if (!key) return null;
    const storageKey = 'sp_interval_' + key;
    try {
      const localValue = localStorage.getItem(storageKey);
      if (localValue) return localValue;
    } catch {
      // Ignore storage read failures.
    }
    try {
      return sessionStorage.getItem(storageKey);
    } catch {
      return null;
    }
  }

  async function syncStatus(params, targetOrCategoryId, silent) {
    let target = targetOrCategoryId;
    if (!target || typeof target !== 'object' || Array.isArray(target)) {
      const categoryIds = Array.isArray(targetOrCategoryId)
        ? targetOrCategoryId
        : targetOrCategoryId
          ? [String(targetOrCategoryId)]
          : params.getTargetCategoryIds();
      target = {
        categoryIds: categoryIds,
        key: params.getTargetKey(categoryIds),
        payload: params.getTargetPayload(categoryIds),
      };
    }
    if (!target.key) {
      if (page.startProtocol && typeof page.startProtocol.ensureCountdownTick === 'function') {
        page.startProtocol.ensureCountdownTick();
      }
      params.updateUI();
      return;
    }

    const data = page.getResponseData(await page.api.getStartProtocolStatus(target.payload));
    const state = params.getState(target.key, target.categoryIds);
    const prevStarted = new Set(state.startedSet || []);
    const nowMs = Date.now();
    const perfNow = performance.now();

    if (!data || (!data.running && !Array.isArray(data.planned))) {
      state.running = false;
      state.planned = null;
      state.startedSet = new Set();
      params.saveAllStates();
      if (page.startProtocol && typeof page.startProtocol.ensureCountdownTick === 'function') {
        page.startProtocol.ensureCountdownTick();
      }
      params.renderList();
      params.updateUI();
      return;
    }

    state.planned = Array.isArray(data.planned) ? data.planned : [];
    state.running = !!data.running;
    state.startedSet = new Set(
      state.planned
        .filter(function (entry) {
          return entry.status === 'STARTED';
        })
        .map(function (entry) {
          return entry.rider_id;
        })
    );

    if (page.state.spEntries.length && Array.isArray(state.planned)) {
      const byRiderId = new Map(
        state.planned.map(function (entry) {
          return [entry.rider_id, entry];
        })
      );
      page.state.spEntries = page.state.spEntries.map(function (entry) {
        const plannedEntry = byRiderId.get(entry.rider_id);
        if (!plannedEntry) return entry;
        return Object.assign({}, entry, {
          status: plannedEntry.status,
          planned_time: plannedEntry.planned_time,
          actual_time: plannedEntry.actual_time,
        });
      });
    }

    if (state.running) state.pausedDelayMs = null;

    state.planned.forEach(function (entry) {
      if (entry.status !== 'STARTED') return;
      const categoryId = String(entry.category_id || '');
      const actualTime = entry.actual_time || entry.planned_time || nowMs;
      if (!categoryId) return;
      const needsTimerBackfill =
        page.state.catTimerElapsed[categoryId] === undefined ||
        page.state.catTimerElapsed[categoryId] === null;
      const isNewStartedRider = !prevStarted.has(entry.rider_id);

      if (!needsTimerBackfill && !isNewStartedRider) return;

      page.setCategoryLifecycleOverride(categoryId, { started: true, closed: false });
      page.state.catTimerElapsed[categoryId] = Math.max(0, nowMs - actualTime);
      page.state.catTimerPerf[categoryId] = perfNow;
      page.state.catTimerClosed[categoryId] = false;
    });

    if (!silent) {
      state.planned.forEach(function (entry) {
        if (entry.status === 'STARTED' && !prevStarted.has(entry.rider_id)) {
          page.toast('СТАРТ: #' + entry.rider_number + ' ' + entry.rider_name);
        }
      });
    }

    params.saveAllStates();
    if (page.startProtocol && typeof page.startProtocol.ensureCountdownTick === 'function') {
      page.startProtocol.ensureCountdownTick();
    }
    if (page.dom && typeof page.dom.updateCategoryTimers === 'function') {
      page.dom.updateCategoryTimers();
    }
    params.renderList();
    params.updateUI();
  }

  async function loadProtocol(params) {
    const target = params.getTarget();
    if (!target.key) {
      page.state.spEntries = [];
      params.renderList();
      params.updateUI();
      return;
    }

    const data = page.getResponseData(await page.api.getStartProtocol(target.payload));
    page.state.spEntries = Array.isArray(data)
      ? data.map(function (entry) {
          return {
            rider_id: entry.rider_id,
            category_id: entry.category_id,
            category_name:
              entry.category_name || page.categoryNames[String(entry.category_id)] || '',
            rider_number: entry.rider_number,
            last_name: entry.last_name || '',
            first_name: entry.first_name || '',
            entry_id: entry.id || entry.entry_id,
            status: entry.status,
          };
        })
      : [];

    await params.syncStatus(target, true);
    if (page.startProtocol && typeof page.startProtocol.ensureCountdownTick === 'function') {
      page.startProtocol.ensureCountdownTick();
    }
    params.renderList();
  }

  async function saveToServer(params) {
    if (!(await page.ensureJudgeAuth('Saving protocol requires login'))) return;
    const target = params.getTarget();
    if (!target.key) return;
    const interval =
      parseInt(page.els.spInterval.value, 10) || page.constants.START_PROTOCOL_INTERVAL_SEC;

    if (target.isMulti) {
      await page.api.saveStartProtocol({
        category_ids: target.payload.category_ids,
        interval_sec: interval,
        entries: page.state.spEntries.map(function (entry) {
          return {
            rider_id: entry.rider_id,
            category_id: entry.category_id,
          };
        }),
      });
      return;
    }

    await page.api.saveStartProtocol(
      target.payload.category_id,
      interval,
      page.state.spEntries.map(function (entry) {
        return entry.rider_id;
      })
    );
  }

  async function autoFill(params) {
    if (!(await page.ensureJudgeAuth())) return;
    const target = params.getTarget();
    if (!target.key) {
      page.toast('Сначала выберите категории', true);
      return;
    }
    if (target.categoryIds.some(params.isLockedByMassStart)) {
      page.toast('Для выбранных категорий индивидуальный протокол недоступен', true);
      return;
    }
    const interval =
      parseInt(page.els.spInterval.value, 10) || page.constants.START_PROTOCOL_INTERVAL_SEC;
    const payload = Object.assign({}, target.payload, { interval_sec: interval });
    const result = await page.api.autoFillStartProtocol(payload);
    if (page.isResponseOk(result)) {
      const data = page.getResponseData(result) || {};
      page.toast('Протокол заполнен: ' + (data.count || 0) + ' участников');
      await params.loadProtocol();
      return;
    }
    page.toast(page.getResponseError(result), true);
  }

  async function clear(params) {
    if (!(await page.ensureJudgeAuth('Clearing protocol requires login'))) return;
    const target = params.getTarget();
    if (!target.key) return;
    if (params.isRunning(target.key)) {
      page.toast('Остановите протокол перед очисткой', true);
      return;
    }
    if (!window.confirm('Очистить стартовый протокол?')) return;
    await page.api.clearStartProtocol(target.payload);
    page.state.spEntries = [];
    params.clearStateFor(target.key);
    params.renderList();
    params.updateUI();
    page.toast('Протокол очищен');
  }

  function switchToCategory(params) {
    const target = params.getTarget();
    if (typeof page.syncCurrentCategoryLifecycle === 'function') {
      page.syncCurrentCategoryLifecycle(page.getCatId());
    }
    if (target.key) {
      const saved = getStoredProtocolInterval(target.key);
      if (saved) page.els.spInterval.value = saved;
    } else {
      page.state.spEntries = [];
      page.els.spSearch.value = '';
      if (page.state.spDropdown) page.state.spDropdown.close();
    }
    params.loadProtocol();
    params.updateUI();
  }

  page.startProtocolActions = {
    syncStatus: syncStatus,
    loadProtocol: loadProtocol,
    saveToServer: saveToServer,
    autoFill: autoFill,
    clear: clear,
    switchToCategory: switchToCategory,
  };
})();
