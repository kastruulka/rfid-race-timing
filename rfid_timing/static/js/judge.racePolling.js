(function () {
  const page = window.JudgePage || (window.JudgePage = {});

  async function loadRiders() {
    page.stateStore.setRiders(page.getResponseData(await page.api.getRiders()));
  }

  async function loadCategoriesAndRestore() {
    const categories = page.stateStore.applyCategoryList(
      page.getResponseData(await page.api.getCategories())
    );
    page.dom.renderRaceCategoryOptions(categories);
    page.dom.restoreSelectedCategory(categories);

    if (page.renderMassStartCategoryOptions) page.renderMassStartCategoryOptions();
    if (page.startProtocol && page.startProtocol.renderCategoryOptions) {
      page.startProtocol.renderCategoryOptions();
    }
    await loadRaceStatus();
    page.dom.updateCategoryTimers();
  }

  function resolveProtocolTargetIds(catId) {
    if (
      page.state.startMode === 'individual' &&
      page.startProtocol &&
      page.startProtocol.getTargetCategoryIds
    ) {
      return page.startProtocol.getTargetCategoryIds();
    }
    return catId ? [catId] : [];
  }

  function syncProtocolStatus(catId, protocolTargetIds) {
    if (page.state.startMode === 'individual' && protocolTargetIds.length) {
      Promise.resolve(page.startProtocol.syncStatus(protocolTargetIds, false)).catch(function () {
        // Ignore protocol status sync failures so race-state polling keeps running.
      });
      return;
    }
    if (!catId) page.startProtocol.updateUI();
  }

  async function loadRaceStatus() {
    startTimerTick();
    if (page.state.raceStatusRequestInFlight) {
      page.state.raceStatusReloadRequested = true;
      return;
    }
    page.state.raceStatusRequestInFlight = true;
    page.state.raceStatusReloadRequested = false;

    const catId = page.getCatId();
    if (catId) sessionStorage.setItem('judge_cat_id', catId);

    try {
      const data = page.getResponseData(await page.api.getRaceState(catId));
      const raceView = page.stateStore.applyRaceState(data, catId, performance.now());
      const protocolTargetIds = resolveProtocolTargetIds(catId);

      if (page.updateMassStartControls) page.updateMassStartControls();
      page.dom.updateCategoryTimers();

      if (!catId) {
        syncProtocolStatus(catId, protocolTargetIds);
        page.dom.applyEmptyRaceStatusView();
        return;
      }

      page.dom.applyRaceStatusView({
        catId: catId,
        status: raceView.status,
        lifecycle: raceView.lifecycle,
        protocolTargetIds: protocolTargetIds,
      });
      syncProtocolStatus(catId, protocolTargetIds);
    } catch {
      // ignore
    } finally {
      page.state.raceStatusRequestInFlight = false;
      if (page.state.raceStatusReloadRequested) {
        page.state.raceStatusReloadRequested = false;
        window.setTimeout(loadRaceStatus, 0);
      }
    }
  }

  function startTimerTick() {
    if (page.state.globalTimerRef) return;
    page.state.globalTimerRef = window.setInterval(
      page.dom.updateCategoryTimers,
      page.constants.TIMER_TICK_MS
    );
  }

  function startPolling() {
    if (!page.state.pollingRefs.log) {
      page.state.pollingRefs.log = window.setInterval(
        page.actions.loadLog,
        page.constants.LOG_POLL_MS
      );
    }
    if (!page.state.pollingRefs.race) {
      page.state.pollingRefs.race = window.setInterval(
        loadRaceStatus,
        page.constants.RACE_STATUS_POLL_MS
      );
    }
    if (!page.state.pollingRefs.riderPanel) {
      page.state.pollingRefs.riderPanel = window.setInterval(function () {
        if (!page.state.selectedRiderId) return;
        const active = document.activeElement;
        if (active && active.tagName === 'INPUT' && active.closest('#laps-section')) return;
        page.riderPanel.refreshRiderPanel();
      }, page.constants.RIDER_PANEL_POLL_MS);
    }
  }

  function stopPolling() {
    Object.keys(page.state.pollingRefs).forEach(function (key) {
      if (page.state.pollingRefs[key]) {
        window.clearInterval(page.state.pollingRefs[key]);
        page.state.pollingRefs[key] = null;
      }
    });
  }

  page.racePolling = {
    loadRiders: loadRiders,
    loadCategoriesAndRestore: loadCategoriesAndRestore,
    selectCategory: page.dom.selectCategory,
    loadRaceStatus: loadRaceStatus,
    startTimerTick: startTimerTick,
    startPolling: startPolling,
    stopPolling: stopPolling,
  };
})();
