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

  function persistProtocolInterval(key, value) {
    if (!key) return;
    const storageKey = 'sp_interval_' + key;
    try {
      localStorage.setItem(storageKey, value);
    } catch {
      // Ignore storage write failures.
    }
    try {
      sessionStorage.setItem(storageKey, value);
    } catch {
      // Ignore storage write failures.
    }
  }

  function getProtocolIntervalTargetKey() {
    const ids =
      page.startProtocol && page.startProtocol.getTargetCategoryIds
        ? page.startProtocol.getTargetCategoryIds()
        : page.getCatId()
          ? [page.getCatId()]
          : [];
    if (!ids.length) return '';
    return ids.length === 1 ? String(ids[0]) : 'multi:' + ids.join(',');
  }

  function getStoredJudgeStartMode() {
    try {
      const localValue = localStorage.getItem('judge_start_mode');
      if (localValue) return localValue;
    } catch {
      // Ignore storage read failures.
    }
    try {
      return sessionStorage.getItem('judge_start_mode');
    } catch {
      return null;
    }
  }

  function bind() {
    page.judgeActions.bindActionButtons();
    page.judgeActions.bindSubmitShortcuts();
    page.els.catTimers.addEventListener('click', function (event) {
      const row = event.target.closest('[data-cat-id]');
      if (!row) return;
      page.racePolling.selectCategory(row.dataset.catId);
    });
    page.els.catTimers.addEventListener('keydown', function (event) {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      const row = event.target.closest('[data-cat-id]');
      if (!row) return;
      event.preventDefault();
      page.racePolling.selectCategory(row.dataset.catId);
    });
    page.els.raceCategory.addEventListener('change', function () {
      page.syncCurrentCategoryLifecycle(page.getCatId());
      page.massStart.updateControls();
      page.racePolling.loadRaceStatus();
      if (page.state.startMode === 'individual') page.startProtocol.switchToCategory();
    });
    page.els.spInterval.addEventListener('change', function () {
      const key = getProtocolIntervalTargetKey();
      if (key) persistProtocolInterval(key, this.value);
      page.startProtocol.renderList();
    });
    page.els.spInterval.addEventListener('input', function () {
      const key = getProtocolIntervalTargetKey();
      if (key) persistProtocolInterval(key, this.value);
      page.startProtocol.renderList();
    });
  }

  function destroy() {
    document.removeEventListener('visibilitychange', handleVisibilityChange);
    window.removeEventListener('beforeunload', destroy);
    page.racePolling.stopPolling();
    if (page.state.globalTimerRef) {
      window.clearInterval(page.state.globalTimerRef);
      page.state.globalTimerRef = null;
    }
    if (page.state.spCountdownTimer) {
      window.clearInterval(page.state.spCountdownTimer);
      page.state.spCountdownTimer = null;
    }
  }

  function handleVisibilityChange() {
    if (document.hidden) {
      page.racePolling.stopPolling();
      return;
    }
    page.racePolling.startTimerTick();
    page.startProtocol.ensureCountdownTick();
    page.dom.updateCategoryTimers();
    page.racePolling.loadRaceStatus();
    page.logNotes.loadLog();
    page.racePolling.startPolling();
  }

  async function init() {
    const savedMode = getStoredJudgeStartMode() || 'mass';
    page.judgeRaceActions.setStartMode(savedMode, { persist: false, syncProtocol: false });

    page.state.authManager = createAuthManager({
      toast: page.toast,
      loginButtonId: 'login-btn',
      logoutButtonId: 'logout-btn',
      authHintId: 'auth-hint',
      onAuthChange: function () {
        page.racePolling.loadRaceStatus();
        page.startProtocol.updateUI();
      },
    });
    page.state.http = createAuthHttpClient({ authManager: page.state.authManager });

    bind();
    page.startProtocol.bind();
    page.riderPanel.bind();
    page.logNotes.bind();

    try {
      await page.state.authManager.checkAuth();
      await Promise.all([
        page.racePolling.loadRiders(),
        page.logNotes.loadLog(),
        page.logNotes.loadNotes(),
        page.racePolling.loadCategoriesAndRestore(),
      ]);
      page.startProtocol.restoreAllStates();

      const savedMassScope = sessionStorage.getItem('judge_mass_start_scope');
      const savedIndividualScope = sessionStorage.getItem('judge_individual_start_scope');
      const savedProtocolRunMode = sessionStorage.getItem('judge_sp_run_mode');
      if (savedMassScope && page.els.massStartScope) page.els.massStartScope.value = savedMassScope;
      if (savedIndividualScope && page.els.individualStartScope) {
        page.els.individualStartScope.value = savedIndividualScope;
      }
      if (savedProtocolRunMode && page.els.spRunMode) {
        page.els.spRunMode.value = savedProtocolRunMode;
      }
      page.massStart.updateScopeUI();
      if (page.startProtocol.updateScopeUI) page.startProtocol.updateScopeUI();
      page.judgeRaceActions.setStartMode(savedMode, { persist: false, syncProtocol: false });
      const intervalKey = getProtocolIntervalTargetKey();
      const savedInterval = getStoredProtocolInterval(intervalKey);
      if (savedInterval) page.els.spInterval.value = savedInterval;
      await page.startProtocol.loadProtocol();
      if (savedMode === 'individual') page.startProtocol.updateUI();
      page.massStart.updateControls();

      page.racePolling.startTimerTick();
      page.startProtocol.ensureCountdownTick();
      page.racePolling.startPolling();
      document.addEventListener('visibilitychange', handleVisibilityChange);
      window.addEventListener('beforeunload', destroy);
    } finally {
      window.pageHydration.finish();
    }
  }

  page.bootstrap = {
    init: init,
    destroy: destroy,
  };
})();
