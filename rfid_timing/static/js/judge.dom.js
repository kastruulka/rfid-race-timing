(function () {
  const page = window.JudgePage || (window.JudgePage = {});

  page.els = {
    raceControl: document.getElementById('race-control'),
    raceCategory: document.getElementById('race-category'),
    raceStatusBar: document.getElementById('race-status-bar'),
    raceStatusRacing: document.getElementById('rs-racing'),
    raceStatusFinished: document.getElementById('rs-finished'),
    raceStatusDnf: document.getElementById('rs-dnf'),
    catTimers: document.getElementById('cat-timers'),
    btnModeMass: document.getElementById('btn-mode-mass'),
    btnModeIndividual: document.getElementById('btn-mode-individual'),
    massStartSection: document.getElementById('mass-start-section'),
    massStartScope: document.getElementById('mass-start-scope'),
    massStartSelectedWrap: document.getElementById('mass-start-selected-wrap'),
    massStartCategoryList: document.getElementById('mass-start-category-list'),
    individualStartSection: document.getElementById('individual-start-section'),
    individualStartScope: document.getElementById('individual-start-scope'),
    individualStartSelectedWrap: document.getElementById('individual-start-selected-wrap'),
    individualStartCategoryList: document.getElementById('individual-start-category-list'),
    btnMassStart: document.getElementById('btn-mass-start'),
    btnFinishRace: document.getElementById('btn-finish-race'),
    btnFinishRaceInd: document.getElementById('btn-finish-race-ind'),
    btnResetCat: document.getElementById('btn-reset-cat'),
    btnNewRace: document.getElementById('btn-new-race'),
    btnSpAutoFill: document.getElementById('btn-sp-autofill'),
    btnSpClear: document.getElementById('btn-sp-clear'),
    spRunMode: document.getElementById('sp-run-mode'),
    spInterval: document.getElementById('sp-interval'),
    spSearch: document.getElementById('sp-search'),
    spDropdown: document.getElementById('sp-dropdown'),
    spList: document.getElementById('sp-list'),
    spCountdownArea: document.getElementById('sp-countdown-area'),
    spCountdownTimer: document.getElementById('sp-countdown-timer'),
    spNextInfo: document.getElementById('sp-next-info'),
    btnSpLaunch: document.getElementById('btn-sp-launch'),
    btnSpStop: document.getElementById('btn-sp-stop'),
    btnIndividualStart: document.getElementById('btn-individual-start'),
    btnAddManualLap: document.getElementById('btn-add-manual-lap'),
    btnEditFinishTime: document.getElementById('btn-edit-finish-time'),
    btnUnfinishRider: document.getElementById('btn-unfinish-rider'),
    btnDnfVoluntary: document.getElementById('btn-dnf-voluntary'),
    btnDnfMechanical: document.getElementById('btn-dnf-mechanical'),
    btnDnfInjury: document.getElementById('btn-dnf-injury'),
    btnTimePenalty: document.getElementById('btn-time-penalty'),
    btnDsq: document.getElementById('btn-dsq'),
    btnExtraLap: document.getElementById('btn-extra-lap'),
    btnWarning: document.getElementById('btn-warning'),
    btnAddNote: document.getElementById('btn-add-note'),
    riderSearch: document.getElementById('rider-search'),
    riderDropdown: document.getElementById('rider-dropdown'),
    searchFilterCat: document.getElementById('search-filter-cat'),
    selectedInfo: document.getElementById('selected-info'),
    srNum: document.getElementById('sr-num'),
    srName: document.getElementById('sr-name'),
    srMeta: document.getElementById('sr-meta'),
    srStatus: document.getElementById('sr-status'),
    currentFinishInfo: document.getElementById('current-finish-info'),
    noFinishInfo: document.getElementById('no-finish-info'),
    currentFinishTime: document.getElementById('current-finish-time'),
    editFinishMm: document.getElementById('edit-finish-mm'),
    editFinishSs: document.getElementById('edit-finish-ss'),
    lapsList: document.getElementById('laps-list'),
    logList: document.getElementById('log-list'),
    noteText: document.getElementById('note-text'),
    notesList: document.getElementById('notes-list'),
    penSeconds: document.getElementById('pen-seconds'),
    penReason: document.getElementById('pen-reason'),
    dsqReason: document.getElementById('dsq-reason'),
    extraLaps: document.getElementById('extra-laps'),
    extraReason: document.getElementById('extra-reason'),
    warnReason: document.getElementById('warn-reason'),
  };

  page.getCatId = function getCatId() {
    return page.els.raceCategory.value;
  };

  page.fmtMs = function fmtMs(ms) {
    if (ms === null || ms === undefined) return '—';
    const totalSec = Math.abs(ms) / 1000;
    const minutes = Math.floor(totalSec / 60);
    const seconds = totalSec % 60;
    return String(minutes).padStart(2, '0') + ':' + seconds.toFixed(1).padStart(4, '0');
  };

  page.setStateDisabled = function setStateDisabled(el, disabled) {
    if (!el) return;
    const stateValue = disabled ? 'true' : 'false';
    const authLocked = !page.state.authManager || !page.state.authManager.state.authenticated;
    const finalDisabled = authLocked || !!disabled;
    const ariaValue = finalDisabled ? 'true' : 'false';
    if (el.dataset.stateDisabled !== stateValue) el.dataset.stateDisabled = stateValue;
    if ('disabled' in el && el.disabled !== finalDisabled) el.disabled = finalDisabled;
    if (el.getAttribute('aria-disabled') !== ariaValue) el.setAttribute('aria-disabled', ariaValue);
    el.style.pointerEvents = finalDisabled ? 'none' : '';
    el.style.opacity = finalDisabled ? '0.55' : '';
    el.style.cursor = finalDisabled ? 'not-allowed' : '';
    el.classList.toggle('is-disabled', finalDisabled);
  };

  page.setSectionStateDisabled = function setSectionStateDisabled(selector, disabled, excludeIds) {
    const exclude = new Set(excludeIds || []);
    document.querySelectorAll(selector).forEach(function (el) {
      if (exclude.has(el.id)) return;
      page.setStateDisabled(el, disabled);
    });
  };

  page.ensureProtocolCategory = function ensureProtocolCategory(message) {
    if (!page.getCatId()) {
      page.toast(message || page.messages.selectProtocolCategory, true);
      return false;
    }
    return true;
  };

  function emptyTimersText() {
    return 'Нет запущенных категорий';
  }

  function renderRaceCategoryOptions(categories) {
    page.els.raceCategory.innerHTML = '<option value="">-- Выберите категорию --</option>';
    (Array.isArray(categories) ? categories : []).forEach(function (cat) {
      const option = document.createElement('option');
      option.value = cat.id;
      option.textContent = window.formatCategoryLabel(cat);
      page.els.raceCategory.appendChild(option);
    });
  }

  function restoreSelectedCategory(categories) {
    const saved = sessionStorage.getItem('judge_cat_id');
    if (saved && page.els.raceCategory.querySelector('option[value="' + saved + '"]')) {
      page.els.raceCategory.value = saved;
    } else if (Array.isArray(categories) && categories.length === 1) {
      page.els.raceCategory.value = categories[0].id;
    }
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

    Array.from(page.els.catTimers.children).forEach(function (node) {
      const isManagedEmptyState = node.hasAttribute && node.hasAttribute('data-empty-timers');
      const isLegacyEmptyState =
        !node.hasAttribute('data-cat-id') &&
        node.textContent &&
        node.textContent.indexOf('Нет запущенных категорий') !== -1;
      if (isManagedEmptyState || isLegacyEmptyState) node.remove();
    });

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
      let perfRef = page.state.catTimerPerf[cid];
      if (!isClosed && (perfRef === null || perfRef === undefined)) {
        perfRef = performance.now();
        page.state.catTimerPerf[cid] = perfRef;
      }
      let displayMs = elapsed;
      if (!isClosed && perfRef) displayMs = elapsed + (performance.now() - perfRef);

      const isSelected = cid === String(selectedCatId);
      const catName = page.categoryNames[cid] || 'Кат. ' + cid;
      const hasPendingProtocol =
        page.startProtocol && typeof page.startProtocol.hasPendingEntries === 'function'
          ? page.startProtocol.hasPendingEntries([cid])
          : false;
      const isProtocolRunning =
        page.startProtocol && typeof page.startProtocol.isRunning === 'function'
          ? page.startProtocol.isRunning(cid)
          : false;
      const showSpBadge = !isClosed && (hasPendingProtocol || isProtocolRunning);
      const color = isClosed ? 'var(--text-dim)' : isSelected ? 'var(--accent)' : 'var(--green)';
      let row = page.els.catTimers.querySelector('[data-cat-id="' + cid + '"]');
      if (!row) {
        row = createTimerRow(cid);
        page.els.catTimers.appendChild(row);
      }

      row.classList.toggle('is-selected', isSelected);
      row.setAttribute('aria-label', catName);
      row._labelEl.textContent = catName;
      row._labelEl.style.color = color;
      row._timeEl.textContent = page.fmtMs(displayMs);
      row._timeEl.style.color = color;
      row._statusEl.style.display = isClosed ? '' : 'none';
      row._badgeEl.style.display = showSpBadge ? '' : 'none';
    });
  }

  function applyEmptyRaceStatusView() {
    page.els.raceStatusBar.style.visibility = 'hidden';
    page.setStateDisabled(page.els.btnFinishRace, true);
    page.setStateDisabled(page.els.btnFinishRaceInd, true);
    if (page.state.authManager) page.state.authManager.syncProtectedControls();
  }

  function applyRaceStatusView(view) {
    const status = view.status || {};
    const lifecycle = view.lifecycle || { started: false, closed: false };
    const catId = view.catId;
    const protocolTargetIds = view.protocolTargetIds || [];
    const effectivelyClosed = lifecycle.closed;

    page.els.raceStatusRacing.textContent = String(status.RACING || 0);
    page.els.raceStatusFinished.textContent = String(status.FINISHED || 0);
    page.els.raceStatusDnf.textContent = String((status.DNF || 0) + (status.DSQ || 0));
    page.els.raceStatusBar.style.visibility = 'visible';

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
    page.els.btnFinishRaceInd.textContent = effectivelyClosed ? 'Категория закрыта' : '■ Завершить';

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
  }

  page.dom = {
    init: function initDomLayer() {
      return page.els;
    },
    renderRaceCategoryOptions: renderRaceCategoryOptions,
    restoreSelectedCategory: restoreSelectedCategory,
    selectCategory: selectCategory,
    updateCategoryTimers: updateCategoryTimers,
    applyEmptyRaceStatusView: applyEmptyRaceStatusView,
    applyRaceStatusView: applyRaceStatusView,
  };
})();
