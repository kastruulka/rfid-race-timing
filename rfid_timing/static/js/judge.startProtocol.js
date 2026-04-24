(function () {
  const page = window.JudgePage || (window.JudgePage = {});
  const scopeApi = page.startProtocolScope;
  const stateApi = page.startProtocolState;
  const queueApi = page.startProtocolQueue;
  const uiApi = page.startProtocolUi;
  const actionApi = page.startProtocolActions;
  const runtimeApi = page.startProtocolRuntime;

  const getCategoryLifecycle = scopeApi.getCategoryLifecycle;
  const getScope = scopeApi.getScope;

  function getRunMode() {
    return page.els.spRunMode ? page.els.spRunMode.value : 'auto';
  }

  const getStoredSelectedIds = scopeApi.getStoredSelectedIds;
  const saveSelectedIds = scopeApi.saveSelectedIds;
  const getSelectedIds = scopeApi.getSelectedIds;
  const getTargetCategoryIds = scopeApi.getTargetCategoryIds;
  const getTargetKey = scopeApi.getTargetKey;
  const getTargetPayload = scopeApi.getTargetPayload;
  const getTarget = scopeApi.getTarget;

  const isPendingProtocolEntry = queueApi.isPendingProtocolEntry;

  const getState = stateApi.getState;
  const isRunning = stateApi.isRunning;
  const hasProtocolPlan = queueApi.hasProtocolPlan;
  const isLockedByMassStart = scopeApi.isLockedByMassStart;
  const saveAllStates = stateApi.saveAllStates;
  const restoreAllStates = stateApi.restoreAllStates;
  const clearStateFor = stateApi.clearStateFor;
  const clearStatesForCategory = stateApi.clearStatesForCategory;
  const getAvailableRiders = queueApi.getAvailableRiders;
  const hasPendingEntries = queueApi.hasPendingEntries;
  const computePausedDelayMs = queueApi.computePausedDelayMs;
  const getNextQueueEntry = queueApi.getNextQueueEntry;
  function removeEntry(index) {
    return runtimeApi.removeEntry(
      {
        getTarget: getTarget,
        getState: getState,
        isRunning: isRunning,
        renderList: renderList,
        saveToServer: saveToServer,
      },
      index
    );
  }

  async function syncStatus(targetOrCategoryId, silent) {
    return actionApi.syncStatus(
      {
        getTargetCategoryIds: getTargetCategoryIds,
        getTargetKey: getTargetKey,
        getTargetPayload: getTargetPayload,
        getState: getState,
        saveAllStates: saveAllStates,
        renderList: renderList,
        updateUI: updateUI,
      },
      targetOrCategoryId,
      silent
    );
  }

  async function loadProtocol() {
    return actionApi.loadProtocol({
      getTarget: getTarget,
      renderList: renderList,
      updateUI: updateUI,
      syncStatus: syncStatus,
    });
  }

  async function saveToServer() {
    return actionApi.saveToServer({
      getTarget: getTarget,
    });
  }

  async function autoFill() {
    return actionApi.autoFill({
      getTarget: getTarget,
      isLockedByMassStart: isLockedByMassStart,
      loadProtocol: loadProtocol,
    });
  }

  async function clear() {
    return actionApi.clear({
      getTarget: getTarget,
      isRunning: isRunning,
      clearStateFor: clearStateFor,
      renderList: renderList,
      updateUI: updateUI,
    });
  }

  function switchToCategory() {
    return actionApi.switchToCategory({
      getTarget: getTarget,
      loadProtocol: loadProtocol,
      updateUI: updateUI,
    });
  }

  function renderCategoryOptions() {
    uiApi.renderCategoryOptions({
      listEl: page.els.individualStartCategoryList,
      categoryNames: page.categoryNames,
      getStoredSelectedIds: getStoredSelectedIds,
    });
  }

  function updateScopeUI() {
    uiApi.updateScopeUI({
      selectedWrapEl: page.els.individualStartSelectedWrap,
      getScope: getScope,
    });
  }

  function renderEmptyState(text) {
    if (text && typeof text === 'object' && Object.prototype.hasOwnProperty.call(text, 'text')) {
      uiApi.renderEmptyState(text);
      return;
    }
    uiApi.renderEmptyState({
      listEl: page.els.spList,
      text: text,
    });
  }

  function renderList() {
    uiApi.renderList({
      getTarget: getTarget,
      getState: getState,
      isRunning: isRunning,
      isPendingProtocolEntry: isPendingProtocolEntry,
      renderEmptyState: renderEmptyState,
      saveToServer: saveToServer,
      renderList: renderList,
    });
  }

  function updateCountdownDisplay(target) {
    uiApi.updateCountdownDisplay({
      target: target,
      isPendingProtocolEntry: isPendingProtocolEntry,
    });
  }

  function updateUI() {
    uiApi.updateUI({
      updateScopeUI: updateScopeUI,
      getTarget: getTarget,
      getState: getState,
      getRunMode: getRunMode,
      isRunning: isRunning,
      hasPendingEntries: hasPendingEntries,
      isLockedByMassStart: isLockedByMassStart,
      getCategoryLifecycle: getCategoryLifecycle,
      updateCountdownDisplay: updateCountdownDisplay,
      isPendingProtocolEntry: isPendingProtocolEntry,
    });
  }

  async function manualStartNext(existingTarget) {
    return runtimeApi.manualStartNext(
      {
        getTarget: getTarget,
        saveToServer: saveToServer,
        loadProtocol: loadProtocol,
        getNextQueueEntry: getNextQueueEntry,
        syncStatus: syncStatus,
      },
      existingTarget
    );
  }

  async function launch() {
    return runtimeApi.launch({
      getTarget: getTarget,
      isLockedByMassStart: isLockedByMassStart,
      getRunMode: getRunMode,
      manualStartNext: manualStartNext,
      getState: getState,
      getCategoryLifecycle: getCategoryLifecycle,
      saveToServer: saveToServer,
      syncStatus: syncStatus,
    });
  }

  async function stop() {
    return runtimeApi.stop({
      getTarget: getTarget,
      computePausedDelayMs: computePausedDelayMs,
      clearStateFor: clearStateFor,
      getState: getState,
      saveAllStates: saveAllStates,
      updateUI: updateUI,
    });
  }

  function ensureCountdownTick() {
    runtimeApi.ensureCountdownTick({
      updateUI: updateUI,
    });
  }

  function bind() {
    runtimeApi.bind({
      updateScopeUI: updateScopeUI,
      switchToCategory: switchToCategory,
      saveSelectedIds: saveSelectedIds,
      getSelectedIds: getSelectedIds,
      updateUI: updateUI,
      removeEntry: removeEntry,
      getTarget: getTarget,
      getState: getState,
      isRunning: isRunning,
      getTargetCategoryIds: getTargetCategoryIds,
      getAvailableRiders: getAvailableRiders,
      isLockedByMassStart: isLockedByMassStart,
      renderList: renderList,
      saveToServer: saveToServer,
    });
  }

  page.startProtocol = {
    bind: bind,
    getState: getState,
    isRunning: isRunning,
    ensureCountdownTick: ensureCountdownTick,
    syncStatus: syncStatus,
    saveAllStates: saveAllStates,
    restoreAllStates: restoreAllStates,
    clearStateFor: clearStateFor,
    clearStatesForCategory: clearStatesForCategory,
    autoFill: autoFill,
    clear: clear,
    loadProtocol: loadProtocol,
    saveToServer: saveToServer,
    switchToCategory: switchToCategory,
    renderList: renderList,
    updateUI: updateUI,
    updateScopeUI: updateScopeUI,
    renderCategoryOptions: renderCategoryOptions,
    getRunMode: getRunMode,
    launch: launch,
    manualStartNext: manualStartNext,
    stop: stop,
    hasPendingEntries: hasPendingEntries,
    computePausedDelayMs: computePausedDelayMs,
    hasProtocolPlan: hasProtocolPlan,
    isLockedByMassStart: isLockedByMassStart,
    getTargetCategoryIds: getTargetCategoryIds,
  };
})();
