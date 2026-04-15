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
    riderPanelRequestInFlight: false,
    lastLapsHash: '',
    pollingRefs: { log: null, race: null, riderPanel: null },
  };
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
  page.categoryNames = {};

  page.getCatId = function getCatId() {
    return page.els.raceCategory.value;
  };
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
})();
