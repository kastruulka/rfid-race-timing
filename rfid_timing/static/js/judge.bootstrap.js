(function () {
  const page = window.JudgePage || (window.JudgePage = {});

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
      const ids =
        page.startProtocol && page.startProtocol.getTargetCategoryIds
          ? page.startProtocol.getTargetCategoryIds()
          : page.getCatId()
            ? [page.getCatId()]
            : [];
      if (ids.length) {
        const key = ids.length === 1 ? String(ids[0]) : 'multi:' + ids.join(',');
        sessionStorage.setItem('sp_interval_' + key, this.value);
      }
      page.startProtocol.renderList();
    });
    page.els.spInterval.addEventListener('input', function () {
      const ids =
        page.startProtocol && page.startProtocol.getTargetCategoryIds
          ? page.startProtocol.getTargetCategoryIds()
          : page.getCatId()
            ? [page.getCatId()]
            : [];
      if (ids.length) {
        const key = ids.length === 1 ? String(ids[0]) : 'multi:' + ids.join(',');
        sessionStorage.setItem('sp_interval_' + key, this.value);
      }
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
    page.racePolling.loadRaceStatus();
    page.logNotes.loadLog();
    page.racePolling.startPolling();
  }

  async function init() {
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

      const initCat = page.getCatId();
      if (initCat) {
        const saved = sessionStorage.getItem('sp_interval_' + initCat);
        if (saved) page.els.spInterval.value = saved;
      }

      const savedMode = sessionStorage.getItem('judge_start_mode');
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
      if (savedMode === 'individual') page.judgeActions.setStartMode('individual');
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
