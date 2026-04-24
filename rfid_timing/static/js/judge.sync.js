(function () {
  const page = window.JudgePage || (window.JudgePage = {});

  if (!page.state.categoryLifecycleById) page.state.categoryLifecycleById = {};
  if (!page.state.categoryLifecycleOverrides) page.state.categoryLifecycleOverrides = {};

  function getDefaultCategoryLifecycle() {
    return { started: false, closed: false };
  }

  function pruneCategoryLifecycleOverrides() {
    Object.keys(page.state.categoryLifecycleOverrides).forEach(function (catId) {
      const override = page.state.categoryLifecycleOverrides[catId];
      const serverState = page.state.categoryLifecycleById[catId] || getDefaultCategoryLifecycle();
      const startedMatches =
        override.started === undefined || override.started === serverState.started;
      const closedMatches = override.closed === undefined || override.closed === serverState.closed;
      if (startedMatches && closedMatches) {
        delete page.state.categoryLifecycleOverrides[catId];
      }
    });
  }

  page.getCategoryLifecycle = function getCategoryLifecycle(catId) {
    const key = String(catId || '');
    const serverState = page.state.categoryLifecycleById[key] || getDefaultCategoryLifecycle();
    const override = page.state.categoryLifecycleOverrides[key] || {};
    return {
      started: override.started !== undefined ? override.started : serverState.started,
      closed: override.closed !== undefined ? override.closed : serverState.closed,
    };
  };

  page.setCategoryLifecycleOverride = function setCategoryLifecycleOverride(catId, patch) {
    if (!catId) return;
    const key = String(catId);
    const prev = page.state.categoryLifecycleOverrides[key] || {};
    page.state.categoryLifecycleOverrides[key] = Object.assign({}, prev, patch || {});
  };

  page.clearCategoryLifecycleOverride = function clearCategoryLifecycleOverride(catId) {
    if (!catId) return;
    delete page.state.categoryLifecycleOverrides[String(catId)];
  };

  page.replaceCategoryLifecycleState = function replaceCategoryLifecycleState(nextState) {
    page.state.categoryLifecycleById = Object.assign({}, nextState || {});
    pruneCategoryLifecycleOverrides();
  };

  page.syncCurrentCategoryLifecycle = function syncCurrentCategoryLifecycle(catId) {
    const lifecycle = page.getCategoryLifecycle(catId);
    page.state.currentCategoryStarted = lifecycle.started;
    page.state.currentCategoryClosed = lifecycle.closed;
    return lifecycle;
  };

  page.runPostActionSync = async function runPostActionSync(options) {
    const opts = Object.assign(
      {
        catId: page.getCatId(),
        lifecyclePatch: null,
        syncProtocolStatus: false,
        clearProtocolState: false,
        clearProtocolEntries: false,
        markTimerClosed: null,
        clearTimer: false,
        updateTimers: false,
        refreshRaceStatus: true,
        refreshRiderPanel: false,
        refreshLog: false,
        refreshNotes: false,
      },
      options || {}
    );

    if (opts.catId && opts.lifecyclePatch) {
      page.setCategoryLifecycleOverride(opts.catId, opts.lifecyclePatch);
      page.syncCurrentCategoryLifecycle(opts.catId);
    }

    if (opts.clearProtocolState && opts.catId) {
      if (page.startProtocol.clearStatesForCategory) {
        page.startProtocol.clearStatesForCategory(opts.catId);
      } else {
        page.startProtocol.clearStateFor(opts.catId);
      }
    }

    if (opts.clearProtocolEntries) {
      page.state.spEntries = [];
      page.startProtocol.renderList();
    }

    if (opts.catId && opts.markTimerClosed !== null) {
      page.state.catTimerClosed[opts.catId] = !!opts.markTimerClosed;
    }

    if (opts.clearTimer && opts.catId) {
      delete page.state.catTimerElapsed[opts.catId];
      delete page.state.catTimerPerf[opts.catId];
      delete page.state.catTimerClosed[opts.catId];
    }

    if (opts.syncProtocolStatus && opts.catId) {
      await page.startProtocol.syncStatus(opts.catId, true);
    }

    page.startProtocol.updateUI();

    if (opts.updateTimers) {
      page.dom.updateCategoryTimers();
    }

    if (opts.refreshRaceStatus) {
      await page.racePolling.loadRaceStatus();
    }

    if (opts.refreshRiderPanel) {
      await page.riderPanel.refreshRiderPanel();
    }

    if (opts.refreshLog) {
      await page.logNotes.loadLog();
    }

    if (opts.refreshNotes) {
      await page.logNotes.loadNotes();
    }
  };
})();
