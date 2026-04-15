(function () {
  const page = window.JudgePage || (window.JudgePage = {});

  function getCategoryLifecycle(catId) {
    if (typeof page.getCategoryLifecycle === 'function') return page.getCategoryLifecycle(catId);
    return {
      started: !!page.state.currentCategoryStarted,
      closed: !!page.state.currentCategoryClosed,
    };
  }

  function getScope() {
    return page.els.individualStartScope ? page.els.individualStartScope.value : 'current';
  }

  function getRunMode() {
    return page.els.spRunMode ? page.els.spRunMode.value : 'auto';
  }

  function getStoredSelectedIds() {
    const raw = sessionStorage.getItem('judge_individual_start_selected') || '';
    return raw
      .split(',')
      .map(function (value) {
        return value.trim();
      })
      .filter(Boolean);
  }

  function saveSelectedIds(ids) {
    sessionStorage.setItem('judge_individual_start_selected', (ids || []).join(','));
  }

  function getSelectedIds() {
    if (!page.els.individualStartCategoryList) return [];
    return Array.from(
      page.els.individualStartCategoryList.querySelectorAll('input[type="checkbox"]:checked')
    ).map(function (input) {
      return String(input.value);
    });
  }

  function getAllCategoryIds() {
    return Object.keys(page.categoryNames || {});
  }

  function getTargetCategoryIds() {
    const scope = getScope();
    if (scope === 'all') return getAllCategoryIds();
    if (scope === 'selected') return getSelectedIds();
    const catId = page.getCatId();
    return catId ? [String(catId)] : [];
  }

  function getTargetKey(categoryIds) {
    const ids = (categoryIds || []).map(String).filter(Boolean);
    if (!ids.length) return '';
    return ids.length === 1 ? ids[0] : 'multi:' + ids.join(',');
  }

  function getTargetPayload(categoryIds) {
    const ids = (categoryIds || []).map(function (catId) {
      return parseInt(catId, 10);
    });
    return ids.length === 1 ? { category_id: ids[0] } : { category_ids: ids };
  }

  function getTarget() {
    const categoryIds = getTargetCategoryIds();
    return {
      categoryIds: categoryIds,
      key: getTargetKey(categoryIds),
      payload: getTargetPayload(categoryIds),
      isMulti: categoryIds.length > 1,
    };
  }

  function getState(key, categoryIds) {
    if (!key) return null;
    if (!page.state.spStates[key]) {
      page.state.spStates[key] = {
        planned: null,
        running: false,
        startedSet: new Set(),
        pausedDelayMs: null,
        categoryIds: (categoryIds || []).map(String),
      };
    }
    if (Array.isArray(categoryIds) && categoryIds.length) {
      page.state.spStates[key].categoryIds = categoryIds.map(String);
    }
    return page.state.spStates[key];
  }

  function isRunning(keyOrCategoryId) {
    const direct = page.state.spStates[String(keyOrCategoryId || '')];
    if (direct) return !!direct.running;
    const categoryId = String(keyOrCategoryId || '');
    if (!categoryId) return false;
    return Object.values(page.state.spStates).some(function (state) {
      return !!(
        state &&
        state.running &&
        Array.isArray(state.categoryIds) &&
        state.categoryIds.includes(categoryId)
      );
    });
  }

  function hasProtocolPlan(catId) {
    if (!catId) return false;
    const categoryId = String(catId);
    if (
      page.state.spEntries.some(function (entry) {
        return String(entry.category_id) === categoryId;
      })
    ) {
      return true;
    }
    return Object.values(page.state.spStates).some(function (state) {
      return !!(
        state &&
        Array.isArray(state.categoryIds) &&
        state.categoryIds.includes(categoryId) &&
        Array.isArray(state.planned) &&
        state.planned.length > 0
      );
    });
  }

  function isLockedByMassStart(catId) {
    const lifecycle = getCategoryLifecycle(catId);
    return !!(catId && lifecycle.started && !lifecycle.closed && !hasProtocolPlan(catId));
  }

  function saveAllStates() {
    const data = {};
    Object.entries(page.state.spStates).forEach(function (item) {
      const key = item[0];
      const state = item[1];
      if (!state || !Array.isArray(state.planned) || !state.planned.length) return;
      data[key] = {
        planned: state.planned,
        startedRiders: Array.from(state.startedSet || []),
        running: !!state.running,
        pausedDelayMs: state.pausedDelayMs,
        categoryIds: state.categoryIds || [],
      };
    });
    if (Object.keys(data).length) sessionStorage.setItem('sp_states', JSON.stringify(data));
    else sessionStorage.removeItem('sp_states');
  }

  function restoreAllStates() {
    try {
      const raw = sessionStorage.getItem('sp_states');
      if (!raw) return false;
      const data = JSON.parse(raw);
      let restored = false;
      Object.entries(data).forEach(function (item) {
        const key = item[0];
        const saved = item[1];
        if (!saved || !Array.isArray(saved.planned) || !saved.planned.length) return;
        const lastPlanned = saved.planned[saved.planned.length - 1].planned_time;
        if (
          saved.running &&
          lastPlanned &&
          Date.now() - lastPlanned > page.constants.START_PROTOCOL_STALE_MS
        ) {
          return;
        }
        const state = getState(key, saved.categoryIds || []);
        state.planned = saved.planned;
        state.startedSet = new Set(saved.startedRiders || []);
        state.running = !!saved.running;
        state.pausedDelayMs = saved.pausedDelayMs ?? null;
        restored = true;
      });
      if (!restored) sessionStorage.removeItem('sp_states');
      return restored;
    } catch {
      return false;
    }
  }

  function clearStateFor(keyOrCategoryIds) {
    const key = Array.isArray(keyOrCategoryIds)
      ? getTargetKey(keyOrCategoryIds)
      : String(keyOrCategoryIds || '');
    if (!key || !page.state.spStates[key]) return;
    page.state.spStates[key].running = false;
    page.state.spStates[key].planned = null;
    page.state.spStates[key].startedSet = new Set();
    page.state.spStates[key].pausedDelayMs = null;
    saveAllStates();
  }

  function getAvailableRiders() {
    const target = getTarget();
    if (!target.categoryIds.length) return [];
    const inList = new Set(
      page.state.spEntries.map(function (entry) {
        return entry.rider_id;
      })
    );
    return page.state.riders.filter(function (rider) {
      if (inList.has(rider.id)) return false;
      if (!target.categoryIds.includes(String(rider.category_id))) return false;
      if (isLockedByMassStart(rider.category_id)) return false;
      return true;
    });
  }

  function hasPendingEntries(keyOrCategoryIds) {
    const key = Array.isArray(keyOrCategoryIds)
      ? getTargetKey(keyOrCategoryIds)
      : String(keyOrCategoryIds || '');
    const state = key ? getState(key) : null;
    return !!(
      key &&
      ((state &&
        Array.isArray(state.planned) &&
        state.planned.some(function (entry) {
          return entry.status !== 'STARTED';
        })) ||
        ((!state || !Array.isArray(state.planned)) && page.state.spEntries.length > 0))
    );
  }

  function computePausedDelayMs(keyOrCategoryIds) {
    const key = Array.isArray(keyOrCategoryIds)
      ? getTargetKey(keyOrCategoryIds)
      : String(keyOrCategoryIds || '');
    const state = key ? getState(key) : null;
    if (!state || !state.running || !Array.isArray(state.planned)) return 0;
    const next = state.planned.find(function (entry) {
      return !state.startedSet.has(entry.rider_id);
    });
    if (!next || next.planned_time === null || next.planned_time === undefined) return 0;
    return Math.max(0, next.planned_time - Date.now());
  }

  function getNextQueueEntry(target) {
    const state = target.key ? getState(target.key, target.categoryIds) : null;
    const startedSet = state ? state.startedSet : new Set();
    return page.state.spEntries.find(function (entry) {
      return !startedSet.has(entry.rider_id);
    });
  }

  function renderCategoryOptions() {
    if (!page.els.individualStartCategoryList) return;
    const selectedIds = new Set(getStoredSelectedIds());
    page.els.individualStartCategoryList.innerHTML = '';
    Object.keys(page.categoryNames).forEach(function (catId) {
      const option = document.createElement('label');
      option.className = 'mass-start-check';

      const input = document.createElement('input');
      input.type = 'checkbox';
      input.value = catId;
      input.checked = selectedIds.has(String(catId));

      const text = document.createElement('span');
      text.textContent = page.categoryNames[catId];

      option.appendChild(input);
      option.appendChild(text);
      page.els.individualStartCategoryList.appendChild(option);
    });
  }

  function updateScopeUI() {
    if (!page.els.individualStartSelectedWrap) return;
    page.els.individualStartSelectedWrap.style.display =
      getScope() === 'selected' ? 'block' : 'none';
  }

  function renderEmptyState(text) {
    page.els.spList.innerHTML = '';
    const empty = document.createElement('div');
    empty.className = 'sp-empty';
    empty.textContent = text;
    page.els.spList.appendChild(empty);
  }

  function dragStart(event) {
    if (!page.requireJudgeEditAccess()) {
      event.preventDefault();
      return;
    }
    page.state.spDragIdx = parseInt(event.currentTarget.dataset.idx, 10);
    event.currentTarget.classList.add('dragging');
  }

  function dragEnd(event) {
    event.currentTarget.classList.remove('dragging');
    document.querySelectorAll('.sp-item').forEach(function (el) {
      el.classList.remove('drag-over');
    });
  }

  function dragOver(event) {
    event.preventDefault();
    const row = event.target.closest('.sp-item');
    if (!row) return;
    document.querySelectorAll('.sp-item').forEach(function (el) {
      el.classList.remove('drag-over');
    });
    row.classList.add('drag-over');
  }

  function drop(event) {
    if (!page.requireJudgeEditAccess()) {
      event.preventDefault();
      return;
    }
    event.preventDefault();
    const row = event.target.closest('.sp-item');
    if (!row) return;
    const dropIdx = parseInt(row.dataset.idx, 10);
    if (page.state.spDragIdx === null || page.state.spDragIdx === dropIdx) return;
    const moved = page.state.spEntries.splice(page.state.spDragIdx, 1)[0];
    page.state.spEntries.splice(dropIdx, 0, moved);
    page.state.spDragIdx = null;
    renderList();
    saveToServer();
  }

  function renderList() {
    const target = getTarget();
    const state = target.key ? getState(target.key, target.categoryIds) : null;
    const interval =
      parseInt(page.els.spInterval.value, 10) || page.constants.START_PROTOCOL_INTERVAL_SEC;
    const startedSet = state ? state.startedSet : new Set();
    const running = target.key ? isRunning(target.key) : false;

    page.els.spList.innerHTML = '';
    if (!target.categoryIds.length) {
      renderEmptyState('Выберите категории, чтобы собрать очередь индивидуального старта');
      return;
    }
    if (!page.state.spEntries.length) {
      renderEmptyState('Протокол пуст. Используйте Авто или добавьте участников вручную.');
      return;
    }

    page.state.spEntries.forEach(function (entry, index) {
      const offsetSec = index * interval;
      const minutes = Math.floor(offsetSec / 60);
      const seconds = offsetSec % 60;
      const timeStr =
        minutes > 0 ? minutes + ':' + String(seconds).padStart(2, '0') : seconds + 'с';
      const isStarted = startedSet.has(entry.rider_id);
      const isNext =
        running && !isStarted && state && Array.isArray(state.planned)
          ? state.planned.findIndex(function (plannedEntry) {
              return !state.startedSet.has(plannedEntry.rider_id);
            }) === index
          : false;
      const canEdit = !running && !isStarted;

      const row = document.createElement('div');
      row.className = 'sp-item';
      if (isStarted) row.classList.add('sp-started');
      if (isNext) row.classList.add('sp-active');
      row.dataset.idx = String(index);
      row.draggable = canEdit;
      row.addEventListener('dragstart', dragStart);
      row.addEventListener('dragend', dragEnd);
      row.addEventListener('dragover', dragOver);
      row.addEventListener('drop', drop);

      row.innerHTML =
        '<span class="sp-pos">' +
        (index + 1) +
        '</span>' +
        '<span class="sp-num">#' +
        entry.rider_number +
        '</span>' +
        '<span class="sp-name">' +
        entry.last_name +
        ' ' +
        entry.first_name +
        '</span>';

      if (target.isMulti) {
        const cat = document.createElement('span');
        cat.className = 'sp-cat';
        cat.textContent =
          entry.category_name || page.categoryNames[String(entry.category_id)] || '';
        row.appendChild(cat);
      }

      const timeEl = document.createElement('span');
      timeEl.className = 'sp-time';
      timeEl.textContent = '+' + timeStr;
      row.appendChild(timeEl);

      if (isStarted) {
        const ok = document.createElement('span');
        ok.style.color = 'var(--green)';
        ok.style.fontSize = '10px';
        ok.style.fontWeight = '700';
        ok.textContent = 'OK';
        row.appendChild(ok);
      } else {
        const del = document.createElement('span');
        del.className = 'sp-del';
        del.dataset.action = 'remove-sp-entry';
        del.dataset.index = String(index);
        del.textContent = 'X';
        row.appendChild(del);
      }

      page.els.spList.appendChild(row);
    });
  }

  function bindSearch() {
    page.state.spDropdown = page.createRiderDropdown({
      inputEl: page.els.spSearch,
      listEl: page.els.spDropdown,
      source: function () {
        if (!getTargetCategoryIds().length) return [];
        const query = String(page.els.spSearch.value || '').toLowerCase();
        return getAvailableRiders().filter(function (rider) {
          if (!query) return true;
          return (
            String(rider.number).includes(query) ||
            String(rider.last_name || '')
              .toLowerCase()
              .includes(query) ||
            String(rider.first_name || '')
              .toLowerCase()
              .includes(query)
          );
        });
      },
      emptyText: function () {
        const targetIds = getTargetCategoryIds();
        if (!targetIds.length) return 'Сначала выберите категории';
        return getAvailableRiders().length === 0 ? 'Все участники уже в протоколе' : 'Не найдено';
      },
      onSelect: function (rider) {
        selectFromSearch(rider.id);
      },
    });
  }

  function selectFromSearch(riderId) {
    if (!page.requireJudgeEditAccess()) return;
    const targetIds = getTargetCategoryIds();
    if (!targetIds.length) {
      page.toast('Сначала выберите категории для индивидуального старта', true);
      return;
    }
    const rider = page.state.riders.find(function (entry) {
      return entry.id === riderId;
    });
    if (!rider) return;
    if (isLockedByMassStart(rider.category_id)) {
      page.toast('Индивидуальный старт недоступен: категория уже запущена массовым стартом', true);
      return;
    }
    if (
      page.state.spEntries.some(function (entry) {
        return entry.rider_id === rider.id;
      })
    ) {
      page.toast('Участник уже в протоколе', true);
      return;
    }

    page.state.spEntries.push({
      rider_id: rider.id,
      category_id: rider.category_id,
      category_name: page.categoryNames[String(rider.category_id)] || '',
      rider_number: rider.number,
      last_name: rider.last_name || '',
      first_name: rider.first_name || '',
    });
    page.state.spDropdown.close();
    page.els.spSearch.value = '';
    renderList();
    saveToServer();
    page.toast('#' + rider.number + ' ' + (rider.last_name || '') + ' добавлен');
  }

  function removeEntry(index) {
    if (!page.requireJudgeEditAccess()) return;
    const target = getTarget();
    const state = target.key ? getState(target.key, target.categoryIds) : null;
    const entry = page.state.spEntries[index];
    if (entry && state && state.startedSet && state.startedSet.has(entry.rider_id)) {
      page.toast('Уже стартовавшего участника нельзя убрать из протокола', true);
      return;
    }
    page.state.spEntries.splice(index, 1);
    renderList();
    saveToServer();
  }

  async function syncStatus(targetOrCategoryId, silent) {
    let target = targetOrCategoryId;
    if (!target || typeof target !== 'object' || Array.isArray(target)) {
      const categoryIds = Array.isArray(targetOrCategoryId)
        ? targetOrCategoryId
        : targetOrCategoryId
          ? [String(targetOrCategoryId)]
          : getTargetCategoryIds();
      target = {
        categoryIds: categoryIds,
        key: getTargetKey(categoryIds),
        payload: getTargetPayload(categoryIds),
      };
    }
    if (!target.key) {
      updateUI();
      return;
    }

    const data = page.getResponseData(await page.api.getStartProtocolStatus(target.payload));
    const state = getState(target.key, target.categoryIds);
    const prevStarted = new Set(state.startedSet || []);

    if (!data || (!data.running && !Array.isArray(data.planned))) {
      state.running = false;
      state.planned = null;
      state.startedSet = new Set();
      saveAllStates();
      renderList();
      updateUI();
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
    if (state.running) state.pausedDelayMs = null;

    if (!silent) {
      state.planned.forEach(function (entry) {
        if (entry.status === 'STARTED' && !prevStarted.has(entry.rider_id)) {
          page.toast('СТАРТ: #' + entry.rider_number + ' ' + entry.rider_name);
        }
      });
    }

    saveAllStates();
    renderList();
    updateUI();
  }

  async function loadProtocol() {
    const target = getTarget();
    if (!target.key) {
      page.state.spEntries = [];
      renderList();
      updateUI();
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

    await syncStatus(target, true);
    renderList();
  }

  async function saveToServer() {
    if (!(await page.ensureJudgeAuth('Saving protocol requires login'))) return;
    const target = getTarget();
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

  async function autoFill() {
    if (!(await page.ensureJudgeAuth())) return;
    const target = getTarget();
    if (!target.key) {
      page.toast('Сначала выберите категории', true);
      return;
    }
    if (target.categoryIds.some(isLockedByMassStart)) {
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
      await loadProtocol();
      return;
    }
    page.toast(page.getResponseError(result), true);
  }

  async function clear() {
    if (!(await page.ensureJudgeAuth('Clearing protocol requires login'))) return;
    const target = getTarget();
    if (!target.key) return;
    if (isRunning(target.key)) {
      page.toast('Остановите протокол перед очисткой', true);
      return;
    }
    if (!window.confirm('Очистить стартовый протокол?')) return;
    await page.api.clearStartProtocol(target.payload);
    page.state.spEntries = [];
    clearStateFor(target.key);
    renderList();
    updateUI();
    page.toast('Протокол очищен');
  }

  function switchToCategory() {
    const target = getTarget();
    if (typeof page.syncCurrentCategoryLifecycle === 'function') {
      page.syncCurrentCategoryLifecycle(page.getCatId());
    }
    if (target.key) {
      const saved = sessionStorage.getItem('sp_interval_' + target.key);
      if (saved) page.els.spInterval.value = saved;
    } else {
      page.state.spEntries = [];
      page.els.spSearch.value = '';
      if (page.state.spDropdown) page.state.spDropdown.close();
    }
    loadProtocol();
    updateUI();
  }

  function updateCountdownDisplay(target) {
    const state = page.state.spStates[target.key];
    if (!state || !Array.isArray(state.planned)) return;
    const next = state.planned.find(function (entry) {
      return !state.startedSet.has(entry.rider_id);
    });
    if (!next) {
      page.els.spCountdownTimer.textContent = '00:00';
      page.els.spCountdownTimer.className = 'sp-countdown go';
      page.els.spNextInfo.textContent = 'Все стартовали';
      return;
    }

    let remain = 0;
    if (state.running) remain = Math.max(0, (next.planned_time || 0) - Date.now());
    else if (state.pausedDelayMs !== null && state.pausedDelayMs !== undefined) {
      remain = Math.max(0, state.pausedDelayMs);
    }

    const sec = remain > 0 ? Math.floor((remain + 999) / 1000) : 0;
    const minutes = Math.floor(sec / 60);
    const seconds = sec % 60;
    page.els.spCountdownTimer.textContent =
      String(minutes).padStart(2, '0') + ':' + String(seconds).padStart(2, '0');
    page.els.spCountdownTimer.className = 'sp-countdown' + (sec <= 3 ? ' go' : '');
    page.els.spNextInfo.innerHTML =
      'Следующий: <b>#' +
      next.rider_number +
      '</b> ' +
      next.rider_name +
      (target.isMulti && next.category_name ? ' [' + next.category_name + ']' : '');
  }

  function updateUI() {
    updateScopeUI();
    const target = getTarget();
    const state = target.key ? getState(target.key, target.categoryIds) : null;
    const runMode = getRunMode();
    const running = target.key ? isRunning(target.key) : false;
    const pending = target.key ? hasPendingEntries(target.key) : false;
    const hasCategories = target.categoryIds.length > 0;
    const hasLockedOnly =
      hasCategories &&
      target.categoryIds.every(function (catId) {
        return isLockedByMassStart(catId);
      });
    const paused = !!(
      state &&
      !state.running &&
      state.pausedDelayMs !== null &&
      pending &&
      !hasLockedOnly
    );
    const showCountdown = runMode === 'auto' && hasCategories && (running || paused);

    page.els.btnSpLaunch.style.display = 'block';
    page.els.btnSpStop.style.display = runMode === 'auto' && running ? 'block' : 'none';
    page.setStateDisabled(
      page.els.btnSpLaunch,
      !hasCategories || hasLockedOnly || !pending || (runMode === 'auto' && running)
    );
    page.setStateDisabled(page.els.btnSpStop, runMode !== 'auto' || !running);
    page.setStateDisabled(page.els.spSearch, !hasCategories || hasLockedOnly || running);
    page.setStateDisabled(page.els.spRunMode, !hasCategories || running);
    page.setStateDisabled(page.els.spInterval, !hasCategories || running || runMode === 'manual');
    page.setStateDisabled(page.els.btnSpAutoFill, !hasCategories || hasLockedOnly || running);
    page.setStateDisabled(page.els.btnSpClear, !hasCategories || running);

    if (runMode === 'manual') {
      page.els.btnSpLaunch.textContent = pending ? '▶ Стартовать следующего' : 'Очередь пуста';
      page.els.spCountdownArea.style.display = 'none';
      page.els.spCountdownTimer.textContent = '00:00';
      page.els.spCountdownTimer.className = 'sp-countdown';
      page.els.spNextInfo.textContent = '';
      return;
    }

    page.els.btnSpLaunch.textContent =
      target.categoryIds.some(function (catId) {
        return getCategoryLifecycle(catId).started;
      }) && pending
        ? '▶ Продолжить протокол'
        : '▶ Запустить протокол';

    page.els.spCountdownArea.style.display = showCountdown ? 'block' : 'none';
    if (!showCountdown) {
      page.els.spCountdownTimer.textContent = '00:00';
      page.els.spCountdownTimer.className = 'sp-countdown';
      page.els.spNextInfo.textContent = '';
      return;
    }
    updateCountdownDisplay(target);
  }

  async function manualStartNext(existingTarget) {
    const target = existingTarget || getTarget();
    if (!target.key) return;

    await saveToServer();
    await loadProtocol();

    const nextEntry = getNextQueueEntry(target);
    if (!nextEntry) {
      page.toast('В очереди не осталось участников для старта', true);
      return;
    }

    const result = await page.api.startProtocolRider({
      rider_id: nextEntry.rider_id,
      entry_id: nextEntry.entry_id,
    });
    if (!page.isResponseOk(result)) {
      page.toast(page.getResponseError(result, 'Ошибка ручного старта'), true);
      return;
    }

    page.setCategoryLifecycleOverride(nextEntry.category_id, { started: true, closed: false });
    await syncStatus(target, true);
    await page.racePolling.loadRaceStatus();
    page.toast('Старт: #' + nextEntry.rider_number + ' ' + nextEntry.last_name);
  }

  async function launch() {
    if (!(await page.ensureJudgeAuth())) return;
    const target = getTarget();
    if (!target.key) {
      page.toast('Сначала выберите категории', true);
      return;
    }
    if (target.categoryIds.some(isLockedByMassStart)) {
      page.toast('Для выбранных категорий индивидуальный протокол недоступен', true);
      return;
    }
    if (!page.state.spEntries.length) {
      page.toast('Протокол пуст', true);
      return;
    }

    if (getRunMode() === 'manual') {
      await manualStartNext(target);
      return;
    }

    const state = getState(target.key, target.categoryIds);
    const isResume = target.categoryIds.some(function (catId) {
      return getCategoryLifecycle(catId).started;
    });
    const resumeDelayMs = isResume && state && state.pausedDelayMs ? state.pausedDelayMs : 0;

    await saveToServer();
    if (!window.confirm((isResume ? 'Продолжить' : 'Запустить') + ' стартовый протокол?')) return;

    const payload = Object.assign({}, target.payload);
    if (resumeDelayMs > 0) payload.resume_delay_ms = resumeDelayMs;
    const result = await page.api.launchStartProtocol(payload);
    if (!page.isResponseOk(result)) {
      page.toast(page.getResponseError(result, 'Ошибка запуска'), true);
      return;
    }

    if (state) state.pausedDelayMs = null;
    target.categoryIds.forEach(function (catId) {
      page.setCategoryLifecycleOverride(catId, { started: true, closed: false });
    });
    await syncStatus(target, true);
    await page.racePolling.loadRaceStatus();
    page.toast(isResume ? 'Протокол продолжен' : 'Протокол запущен');
  }

  async function stop() {
    if (!(await page.ensureJudgeAuth())) return;
    const target = getTarget();
    if (!target.key) return;

    const pausedDelayMs = computePausedDelayMs(target.key);
    const result = await page.api.stopStartProtocol(target.payload);
    if (!page.isResponseOk(result)) {
      page.toast(page.getResponseError(result, 'Ошибка остановки'), true);
      return;
    }

    clearStateFor(target.key);
    const state = getState(target.key, target.categoryIds);
    state.pausedDelayMs = pausedDelayMs;
    saveAllStates();
    updateUI();
    page.toast('Протокол поставлен на паузу');
  }

  function ensureCountdownTick() {
    if (page.state.spCountdownTimer) return;
    page.state.spCountdownTimer = window.setInterval(function () {
      if (page.state.startMode !== 'individual') return;
      updateUI();
    }, page.constants.COUNTDOWN_TICK_MS);
  }

  function bind() {
    bindSearch();

    if (page.els.individualStartScope) {
      page.els.individualStartScope.addEventListener('change', function () {
        sessionStorage.setItem('judge_individual_start_scope', this.value);
        updateScopeUI();
        switchToCategory();
      });
    }

    if (page.els.individualStartCategoryList) {
      page.els.individualStartCategoryList.addEventListener('change', function () {
        saveSelectedIds(getSelectedIds());
        switchToCategory();
      });
    }

    if (page.els.spRunMode) {
      page.els.spRunMode.addEventListener('change', function () {
        sessionStorage.setItem('judge_sp_run_mode', this.value);
        updateUI();
      });
    }

    page.els.spList.addEventListener('click', function (event) {
      const removeBtn = event.target.closest('[data-action="remove-sp-entry"]');
      if (!removeBtn) return;
      removeEntry(parseInt(removeBtn.dataset.index, 10));
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
