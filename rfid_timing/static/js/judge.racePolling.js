(function () {
  const page = window.JudgePage || (window.JudgePage = {});

  function emptyTimersText() {
    return 'Нет запущенных категорий';
  }

  async function loadRiders() {
    const data = page.getResponseData(await page.api.getRiders());
    page.state.riders = Array.isArray(data) ? data : [];
  }

  async function loadCategoriesAndRestore() {
    const cats = page.getResponseData(await page.api.getCategories());
    page.els.raceCategory.innerHTML = '<option value="">-- Выберите категорию --</option>';
    page.categoryNames = {};

    (Array.isArray(cats) ? cats : []).forEach(function (cat) {
      const option = document.createElement('option');
      option.value = cat.id;
      option.textContent = cat.name + ' (' + cat.laps + ' кр.)';
      page.els.raceCategory.appendChild(option);
      page.categoryNames[String(cat.id)] = cat.name;
    });

    const saved = sessionStorage.getItem('judge_cat_id');
    if (saved && page.els.raceCategory.querySelector('option[value="' + saved + '"]')) {
      page.els.raceCategory.value = saved;
    } else if (Array.isArray(cats) && cats.length === 1) {
      page.els.raceCategory.value = cats[0].id;
    }

    if (page.renderMassStartCategoryOptions) page.renderMassStartCategoryOptions();
    if (page.startProtocol && page.startProtocol.renderCategoryOptions) {
      page.startProtocol.renderCategoryOptions();
    }
    await loadRaceStatus();
    updateCategoryTimers();
  }

  function selectCategory(catId) {
    if (!catId) return;
    const nextId = String(catId);
    if (!page.els.raceCategory.querySelector('option[value="' + nextId + '"]')) return;
    if (String(page.getCatId()) === nextId) return;
    page.els.raceCategory.value = nextId;
    page.els.raceCategory.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function createEmptyTimersNode() {
    const empty = document.createElement('div');
    empty.dataset.emptyTimers = 'true';
    empty.style.fontSize = '11px';
    empty.style.color = 'var(--text-dim)';
    empty.style.padding = '4px 0';
    empty.textContent = emptyTimersText();
    return empty;
  }

  function createTimerRow(cid) {
    const row = document.createElement('div');
    row.className = 'cat-timer-item';
    row.dataset.catId = String(cid);
    row.setAttribute('role', 'button');
    row.tabIndex = 0;

    const main = document.createElement('div');
    main.className = 'cat-timer-main';

    const label = document.createElement('span');
    label.className = 'cat-timer-label';

    const time = document.createElement('span');
    time.className = 'cat-timer-time';

    const flags = document.createElement('div');
    flags.className = 'cat-timer-flags';

    const status = document.createElement('span');
    status.className = 'cat-timer-status';
    status.textContent = 'завершена';

    const badge = document.createElement('span');
    badge.className = 'sp-run-badge';
    badge.textContent = 'SP';

    flags.appendChild(status);
    flags.appendChild(badge);
    main.appendChild(label);
    main.appendChild(time);
    row.appendChild(main);
    row.appendChild(flags);

    row._labelEl = label;
    row._timeEl = time;
    row._statusEl = status;
    row._badgeEl = badge;
    return row;
  }

  function ensureEmptyTimersState() {
    page.els.catTimers.innerHTML = '';
    page.els.catTimers.appendChild(createEmptyTimersNode());
  }

  function updateCategoryTimers() {
    const entries = Object.entries(page.state.catTimerElapsed);
    if (!entries.length) {
      ensureEmptyTimersState();
      return;
    }

    const emptyNode = page.els.catTimers.querySelector('[data-empty-timers]');
    if (emptyNode) emptyNode.remove();

    const selectedCatId = page.getCatId();
    const activeIds = new Set(
      entries.map(function (entry) {
        return String(entry[0]);
      })
    );

    Array.from(page.els.catTimers.querySelectorAll('[data-cat-id]')).forEach(function (row) {
      if (!activeIds.has(row.dataset.catId)) row.remove();
    });

    entries.forEach(function (entry) {
      const cid = String(entry[0]);
      const elapsed = entry[1];
      const isClosed = page.state.catTimerClosed[cid] || false;
      const perfRef = page.state.catTimerPerf[cid];
      let displayMs = elapsed;
      if (!isClosed && perfRef) displayMs = elapsed + (performance.now() - perfRef);

      const isSelected = cid === String(selectedCatId);
      const catName = page.categoryNames[cid] || 'РљР°С‚. ' + cid;
      const isSpRun = !isClosed && page.startProtocol.isRunning(cid);
      const color = isClosed ? 'var(--text-dim)' : isSelected ? 'var(--accent)' : 'var(--green)';
      const label = isClosed ? 'вњ“ ' + catName : catName;

      let row = page.els.catTimers.querySelector('[data-cat-id="' + cid + '"]');
      if (!row) {
        row = createTimerRow(cid);
        page.els.catTimers.appendChild(row);
      }

      row.classList.toggle('is-selected', isSelected);
      row.setAttribute('aria-label', 'Открыть категорию ' + label);
      row._labelEl.textContent = label;
      row._labelEl.style.color = color;
      row._timeEl.textContent = page.fmtMs(displayMs);
      row._timeEl.style.color = color;
      row._statusEl.style.display = isClosed ? '' : 'none';
      row._badgeEl.style.display = isSpRun ? '' : 'none';
    });
  }

  function startTimerTick() {
    if (page.state.globalTimerRef) return;
    page.state.globalTimerRef = window.setInterval(
      updateCategoryTimers,
      page.constants.TIMER_TICK_MS
    );
  }

  async function loadRaceStatus() {
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
      const status = data && data.status ? data.status : {};
      const catStates = data && data.category_states ? data.category_states : {};
      const nextLifecycleById = {};

      if (Array.isArray(data && data.categories)) {
        data.categories.forEach(function (cat) {
          page.categoryNames[String(cat.id)] = cat.name;
        });
      }

      const now = performance.now();
      Object.keys(page.state.catTimerElapsed).forEach(function (cid) {
        if (!(cid in catStates)) {
          delete page.state.catTimerElapsed[cid];
          delete page.state.catTimerPerf[cid];
          delete page.state.catTimerClosed[cid];
        }
      });

      Object.entries(catStates).forEach(function (item) {
        const cid = item[0];
        const entry = item[1];
        nextLifecycleById[cid] = {
          started: !!entry.started_at,
          closed: entry.closed === true,
        };
        if (entry.elapsed_ms !== null && entry.elapsed_ms !== undefined) {
          page.state.catTimerElapsed[cid] = entry.elapsed_ms;
          page.state.catTimerPerf[cid] = now;
          page.state.catTimerClosed[cid] = entry.closed;
        }
      });

      if (catId) {
        nextLifecycleById[String(catId)] = {
          started: data.category_started === true,
          closed: data.category_closed === true,
        };
      }

      page.replaceCategoryLifecycleState(nextLifecycleById);
      page.syncCurrentCategoryLifecycle(catId);
      if (page.updateMassStartControls) page.updateMassStartControls();

      updateCategoryTimers();

      if (!catId) {
        page.els.raceStatusBar.style.visibility = 'hidden';
        page.setStateDisabled(page.els.btnFinishRace, true);
        page.setStateDisabled(page.els.btnFinishRaceInd, true);
        if (page.state.authManager) page.state.authManager.syncProtectedControls();
        return;
      }

      page.els.raceStatusRacing.textContent = String(status.RACING || 0);
      page.els.raceStatusFinished.textContent = String(status.FINISHED || 0);
      page.els.raceStatusDnf.textContent = String((status.DNF || 0) + (status.DSQ || 0));
      page.els.raceStatusBar.style.visibility = 'visible';

      const lifecycle = page.syncCurrentCategoryLifecycle(catId);
      const effectivelyClosed = lifecycle.closed;

      page.setStateDisabled(page.els.btnFinishRace, !lifecycle.started || effectivelyClosed);
      page.setStateDisabled(page.els.btnFinishRaceInd, !lifecycle.started || effectivelyClosed);
      page.els.btnMassStart.textContent = effectivelyClosed
        ? 'Категория завершена'
        : lifecycle.started
          ? (status.RACING || 0) > 0
            ? 'Гонка идёт'
            : 'Гонка активна'
          : '▶ Масс-старт';

      if (page.updateMassStartControls) page.updateMassStartControls();
      const protocolTargetIds =
        page.state.startMode === 'individual' &&
        page.startProtocol &&
        page.startProtocol.getTargetCategoryIds
          ? page.startProtocol.getTargetCategoryIds()
          : catId
            ? [catId]
            : [];
      const pendingEntries = page.startProtocol.hasPendingEntries(protocolTargetIds);
      const lockedByMassStart = page.startProtocol.isLockedByMassStart(catId);
      const canLaunch =
        !effectivelyClosed &&
        !lockedByMassStart &&
        !page.startProtocol.isRunning(
          protocolTargetIds.length > 1 ? 'multi:' + protocolTargetIds.join(',') : catId
        ) &&
        pendingEntries;
      page.setStateDisabled(
        page.els.btnIndividualStart,
        effectivelyClosed || lockedByMassStart || !catId
      );
      page.setStateDisabled(page.els.btnSpLaunch, !canLaunch || !catId);
      page.els.btnFinishRace.textContent = effectivelyClosed
        ? 'Категория закрыта'
        : '■ Завершить категорию';
      page.els.btnFinishRaceInd.textContent = effectivelyClosed
        ? 'Категория закрыта'
        : '■ Завершить';

      page.setSectionStateDisabled(
        '#laps-section [data-auth-required], .actions-grid [data-auth-required], .notes-section [data-auth-required]',
        effectivelyClosed,
        [
          'btn-mass-start',
          'btn-finish-race',
          'btn-finish-race-ind',
          'btn-sp-launch',
          'btn-individual-start',
        ]
      );

      if (page.state.authManager) page.state.authManager.syncProtectedControls();
      if (page.state.startMode === 'individual' && protocolTargetIds.length)
        await page.startProtocol.syncStatus(protocolTargetIds, false);
    } catch {
      // ignore polling errors
    } finally {
      page.state.raceStatusRequestInFlight = false;
      if (page.state.raceStatusReloadRequested) {
        page.state.raceStatusReloadRequested = false;
        window.setTimeout(loadRaceStatus, 0);
      }
    }
  }

  function startPolling() {
    if (!page.state.pollingRefs.log)
      page.state.pollingRefs.log = window.setInterval(
        page.actions.loadLog,
        page.constants.LOG_POLL_MS
      );
    if (!page.state.pollingRefs.race)
      page.state.pollingRefs.race = window.setInterval(
        loadRaceStatus,
        page.constants.RACE_STATUS_POLL_MS
      );
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
    selectCategory: selectCategory,
    loadRaceStatus: loadRaceStatus,
    updateCategoryTimers: updateCategoryTimers,
    startTimerTick: startTimerTick,
    startPolling: startPolling,
    stopPolling: stopPolling,
  };
})();
