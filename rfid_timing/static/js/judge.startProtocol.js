(function () {
  const page = window.JudgePage || (window.JudgePage = {});

  function getState(catId) {
    if (!catId) return null;
    if (!page.state.spStates[catId]) {
      page.state.spStates[catId] = {
        entries: [],
        planned: null,
        running: false,
        startedSet: new Set(),
        starting: false,
        pausedDelayMs: null,
      };
    }
    return page.state.spStates[catId];
  }

  function isRunning(catId) {
    const state = page.state.spStates[catId];
    return !!(state && state.running);
  }

  function getCategoryLifecycle(catId) {
    if (typeof page.getCategoryLifecycle === 'function') {
      return page.getCategoryLifecycle(catId);
    }
    return {
      started: !!page.state.currentCategoryStarted,
      closed: !!page.state.currentCategoryClosed,
    };
  }

  function hasProtocolPlan(catId) {
    const state = catId ? getState(catId) : null;
    return !!(
      catId &&
      ((state && Array.isArray(state.planned) && state.planned.length > 0) ||
        page.state.spEntries.length > 0)
    );
  }

  function isLockedByMassStart(catId) {
    const lifecycle = getCategoryLifecycle(catId);
    return !!(catId && lifecycle.started && !lifecycle.closed && !hasProtocolPlan(catId));
  }

  function saveAllStates() {
    const data = {};
    Object.entries(page.state.spStates).forEach(function (entry) {
      const catId = entry[0];
      const state = entry[1];
      if (state.planned && state.planned.length) {
        data[catId] = {
          planned: state.planned,
          startedRiders: Array.from(state.startedSet),
          running: !!state.running,
          pausedDelayMs: state.pausedDelayMs,
        };
      }
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
        const catId = item[0];
        const saved = item[1];
        if (!saved.planned || !saved.planned.length) return;

        const started = new Set(saved.startedRiders || []);
        const remaining = saved.planned.filter(function (entry) {
          return !started.has(entry.rider_id);
        });
        if (!remaining.length) return;

        const lastPlanned = saved.planned[saved.planned.length - 1].planned_time;
        if (
          saved.running &&
          lastPlanned &&
          Date.now() - lastPlanned > page.constants.START_PROTOCOL_STALE_MS
        )
          return;

        const state = getState(catId);
        state.planned = saved.planned;
        state.startedSet = started;
        state.running = !!saved.running;
        state.starting = false;
        state.pausedDelayMs = saved.pausedDelayMs ?? null;
        restored = true;
      });

      if (!restored) sessionStorage.removeItem('sp_states');
      return restored;
    } catch {
      return false;
    }
  }

  function clearStateFor(catId) {
    if (page.state.spStates[catId]) {
      page.state.spStates[catId].running = false;
      page.state.spStates[catId].planned = null;
      page.state.spStates[catId].startedSet = new Set();
      page.state.spStates[catId].starting = false;
      page.state.spStates[catId].pausedDelayMs = null;
    }
    saveAllStates();
  }

  function getAvailableRiders() {
    const catId = page.getCatId();
    if (isLockedByMassStart(catId)) return [];

    const inList = new Set(
      page.state.spEntries.map(function (entry) {
        return entry.rider_id;
      })
    );
    return page.state.riders.filter(function (rider) {
      if (inList.has(rider.id)) return false;
      if (catId && rider.category_id != catId) return false;
      return true;
    });
  }

  function findNextVisualIndex(catId) {
    const state = page.state.spStates[catId];
    if (!state || !state.planned) return -1;
    for (let idx = 0; idx < state.planned.length; idx += 1) {
      if (!state.startedSet.has(state.planned[idx].rider_id)) return idx;
    }
    return -1;
  }

  function hasPendingEntries(catId) {
    const state = catId ? getState(catId) : null;
    return !!(
      catId &&
      ((state &&
        Array.isArray(state.planned) &&
        state.planned.some(function (entry) {
          return entry.status !== 'STARTED';
        })) ||
        ((!state || !Array.isArray(state.planned)) && page.state.spEntries.length > 0))
    );
  }

  function computePausedDelayMs(catId) {
    const state = catId ? getState(catId) : null;
    if (!state || !state.running || !Array.isArray(state.planned)) return 0;

    const next = state.planned.find(function (entry) {
      return !state.startedSet.has(entry.rider_id);
    });
    if (!next || next.planned_time === null || next.planned_time === undefined) return 0;
    return Math.max(0, next.planned_time - Date.now());
  }

  function bindSearch() {
    page.state.spDropdown = page.createRiderDropdown({
      inputEl: page.els.spSearch,
      listEl: page.els.spDropdown,
      source: function () {
        if (!page.getCatId()) return [];
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
        const catId = page.getCatId();
        if (!catId) return 'Сначала выберите категорию';
        if (isLockedByMassStart(catId)) return 'Категория уже запущена массовым стартом';
        return getAvailableRiders().length === 0 ? 'Все участники уже в протоколе' : 'Не найдено';
      },
      onSelect: function (rider) {
        selectFromSearch(rider.id);
      },
    });
  }

  function selectFromSearch(riderId) {
    if (!page.requireJudgeEditAccess()) return;
    if (!page.ensureProtocolCategory()) return;
    if (isLockedByMassStart(page.getCatId())) {
      page.toast('Индивидуальный старт недоступен: категория уже запущена массовым стартом', true);
      return;
    }

    const rider = page.state.riders.find(function (entry) {
      return entry.id === riderId;
    });
    if (!rider) return;
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

  function removeEntry(index) {
    if (!page.requireJudgeEditAccess()) return;
    if (isLockedByMassStart(page.getCatId())) return;

    const entry = page.state.spEntries[index];
    const catId = page.getCatId();
    const state = catId ? getState(catId) : null;
    if (entry && state && state.startedSet && state.startedSet.has(entry.rider_id)) {
      page.toast('Уже стартовавшего участника нельзя убрать из протокола', true);
      return;
    }

    page.state.spEntries.splice(index, 1);
    renderList();
    saveToServer();
  }

  function renderEmptyState(text) {
    page.els.spList.innerHTML = '';
    const empty = document.createElement('div');
    empty.className = 'sp-empty';
    empty.textContent = text;
    page.els.spList.appendChild(empty);
  }

  function renderList() {
    const catId = page.getCatId();
    const lifecycle = getCategoryLifecycle(catId);
    const interval =
      parseInt(page.els.spInterval.value, 10) || page.constants.START_PROTOCOL_INTERVAL_SEC;
    const state = catId ? getState(catId) : null;
    const startedSet = state ? state.startedSet : new Set();
    const running = isRunning(catId);

    page.els.spList.innerHTML = '';
    if (!catId) {
      renderEmptyState('Выберите категорию, чтобы собрать очередь индивидуального старта');
      return;
    }
    if (lifecycle.closed && !page.state.spEntries.length) {
      renderEmptyState('Протокол пуст. Используйте «Авто» или добавьте участников вручную');
      return;
    }
    if (isLockedByMassStart(catId)) {
      renderEmptyState(
        'Индивидуальный протокол недоступен: категория уже запущена массовым стартом.'
      );
      return;
    }
    if (!page.state.spEntries.length) {
      renderEmptyState('Протокол пуст. Используйте «Авто» или добавьте участников вручную.');
      return;
    }

    page.state.spEntries.forEach(function (entry, index) {
      const offsetSec = index * interval;
      const minutes = Math.floor(offsetSec / 60);
      const seconds = offsetSec % 60;
      const timeStr =
        minutes > 0 ? minutes + ':' + String(seconds).padStart(2, '0') : seconds + 'с';
      const isStarted = startedSet.has(entry.rider_id);
      const isNext = running && !isStarted && index === findNextVisualIndex(catId);
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
        '</span>' +
        '<span class="sp-time">+' +
        timeStr +
        '</span>';

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

  async function syncStatus(catId, silent) {
    if (!catId) {
      updateUI();
      return;
    }

    if (getCategoryLifecycle(catId).closed) {
      clearStateFor(catId);
      page.state.spEntries = [];
      renderList();
      updateUI();
      return;
    }

    const data = page.getResponseData(await page.api.getStartProtocolStatus(catId));
    const state = getState(catId);
    const prevRunning = !!state.running;
    const prevPlannedKey = Array.isArray(state.planned)
      ? state.planned
          .map(function (entry) {
            return [
              entry.entry_id || entry.id,
              entry.status,
              entry.planned_time,
              entry.actual_time,
            ].join(':');
          })
          .join('|')
      : '';
    const prevStarted = new Set(state.startedSet || []);

    if (!data || (!data.running && !Array.isArray(data.planned))) {
      const hadProtocol = prevRunning || prevPlannedKey !== '';
      const shouldPreservePaused =
        state.pausedDelayMs !== null &&
        state.pausedDelayMs !== undefined &&
        page.state.spEntries.length > 0 &&
        !getCategoryLifecycle(catId).closed;
      if (shouldPreservePaused) {
        state.running = false;
        saveAllStates();
        updateUI();
        return;
      }
      state.running = false;
      state.planned = null;
      state.startedSet = new Set();
      state.pausedDelayMs = null;
      saveAllStates();
      if (hadProtocol) renderList();
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

    const nextPlannedKey = state.planned
      .map(function (entry) {
        return [
          entry.entry_id || entry.id,
          entry.status,
          entry.planned_time,
          entry.actual_time,
        ].join(':');
      })
      .join('|');
    const startedChanged =
      prevStarted.size !== state.startedSet.size ||
      Array.from(state.startedSet).some(function (riderId) {
        return !prevStarted.has(riderId);
      });
    const protocolChanged = prevRunning !== state.running || prevPlannedKey !== nextPlannedKey;

    if (!silent) {
      state.planned.forEach(function (entry) {
        if (entry.status === 'STARTED' && !prevStarted.has(entry.rider_id)) {
          page.toast('СТАРТ: #' + entry.rider_number + ' ' + entry.rider_name);
        }
      });
    }

    saveAllStates();
    if (protocolChanged || startedChanged) renderList();
    updateUI();
  }

  async function autoFill() {
    if (!(await page.ensureJudgeAuth())) return;
    const catId = page.getCatId();
    if (!catId) {
      page.toast(page.messages.selectCategory, true);
      return;
    }
    if (isRunning(catId)) {
      page.toast('Протокол запущен — остановите сначала', true);
      return;
    }
    if (isLockedByMassStart(catId)) {
      page.toast('Индивидуальный старт недоступен: категория уже запущена массовым стартом', true);
      return;
    }

    const interval =
      parseInt(page.els.spInterval.value, 10) || page.constants.START_PROTOCOL_INTERVAL_SEC;
    const result = await page.api.autoFillStartProtocol(catId, interval);
    if (page.isResponseOk(result)) {
      const data = page.getResponseData(result) || {};
      page.toast('Протокол заполнен: ' + (data.count || 0) + ' участников');
      await loadProtocol();
    } else {
      page.toast(page.getResponseError(result), true);
    }
  }

  async function clear() {
    if (!(await page.ensureJudgeAuth('Clearing protocol requires login'))) return;
    const catId = page.getCatId();
    if (isRunning(catId)) {
      page.toast('Остановите протокол перед очисткой', true);
      return;
    }
    if (!catId) return;
    if (isLockedByMassStart(catId)) {
      page.toast(
        'Индивидуальный протокол недоступен: категория уже запущена массовым стартом',
        true
      );
      return;
    }
    if (!window.confirm('Очистить стартовый протокол?')) return;

    await page.api.clearStartProtocol(catId);
    page.state.spEntries = [];
    renderList();
    page.toast('Протокол очищен');
  }

  async function loadProtocol() {
    const catId = page.getCatId();
    if (!catId) {
      page.state.spEntries = [];
      renderList();
      return;
    }

    const data = page.getResponseData(await page.api.getStartProtocol(catId));
    page.state.spEntries = Array.isArray(data)
      ? data.map(function (entry) {
          return {
            rider_id: entry.rider_id,
            rider_number: entry.rider_number,
            last_name: entry.last_name || '',
            first_name: entry.first_name || '',
            entry_id: entry.id,
            status: entry.status,
          };
        })
      : [];

    await syncStatus(catId, true);
    renderList();
  }

  async function saveToServer() {
    if (!(await page.ensureJudgeAuth('Saving protocol requires login'))) return;
    const catId = page.getCatId();
    if (!catId) return;
    const interval =
      parseInt(page.els.spInterval.value, 10) || page.constants.START_PROTOCOL_INTERVAL_SEC;
    await page.api.saveStartProtocol(
      catId,
      interval,
      page.state.spEntries.map(function (entry) {
        return entry.rider_id;
      })
    );
  }

  function switchToCategory() {
    const catId = page.getCatId();
    if (typeof page.syncCurrentCategoryLifecycle === 'function') {
      page.syncCurrentCategoryLifecycle(catId);
    }
    if (catId) {
      const saved = sessionStorage.getItem('sp_interval_' + catId);
      if (saved) page.els.spInterval.value = saved;
    } else {
      page.state.spEntries = [];
      page.els.spSearch.value = '';
      if (page.state.spDropdown) page.state.spDropdown.close();
    }
    loadProtocol();
    updateUI();
  }

  function updateUI() {
    const catId = page.getCatId();
    const lifecycle = getCategoryLifecycle(catId);
    const state = catId ? getState(catId) : null;
    const running = isRunning(catId);
    const hasCategory = !!catId;
    const lockedByMassStart = isLockedByMassStart(catId);
    const pending = hasPendingEntries(catId);
    const paused = !!(
      state &&
      !state.running &&
      state.pausedDelayMs !== null &&
      pending &&
      !lifecycle.closed &&
      !lockedByMassStart
    );
    const protocolEditable =
      !running &&
      hasCategory &&
      !lifecycle.closed &&
      !lockedByMassStart &&
      (!lifecycle.started || pending);
    const showCountdown =
      hasCategory && !lifecycle.closed && !lockedByMassStart && (running || paused);

    if (lifecycle.closed) {
      page.els.btnSpLaunch.style.display = 'block';
      page.els.btnSpStop.style.display = 'none';
      page.els.spCountdownArea.style.display = 'none';
      page.setStateDisabled(page.els.btnSpLaunch, !hasCategory);
      page.setStateDisabled(page.els.btnSpStop, true);
      page.setStateDisabled(page.els.spSearch, true);
      page.setStateDisabled(page.els.spInterval, true);
      page.setStateDisabled(page.els.btnSpAutoFill, true);
      page.setStateDisabled(page.els.btnSpClear, true);
      page.els.spCountdownTimer.textContent = '00:00';
      page.els.spCountdownTimer.className = 'sp-countdown';
      page.els.spNextInfo.textContent = '';
      return;
    }

    page.els.btnSpLaunch.style.display = running ? 'none' : 'block';
    page.setStateDisabled(
      page.els.btnSpLaunch,
      running || !hasCategory || lifecycle.closed || lockedByMassStart || !pending
    );
    page.els.btnSpStop.style.display = running ? 'block' : 'none';
    page.setStateDisabled(page.els.btnSpStop, !running || lifecycle.closed || lockedByMassStart);
    page.els.spCountdownArea.style.display = showCountdown ? 'block' : 'none';
    page.setStateDisabled(page.els.spSearch, !protocolEditable);
    page.setStateDisabled(page.els.spInterval, !protocolEditable);
    page.setStateDisabled(page.els.btnSpAutoFill, !protocolEditable);
    page.setStateDisabled(page.els.btnSpClear, !protocolEditable);

    if (lockedByMassStart) {
      page.els.spCountdownTimer.textContent = '00:00';
      page.els.spCountdownTimer.className = 'sp-countdown';
      page.els.spNextInfo.textContent = 'Категория уже запущена массовым стартом';
      return;
    }

    if (!showCountdown) {
      page.els.spCountdownTimer.textContent = '00:00';
      page.els.spCountdownTimer.className = 'sp-countdown';
      page.els.spNextInfo.textContent = '';
      return;
    }

    updateCountdownDisplay(catId);
  }

  async function launch() {
    if (!(await page.ensureJudgeAuth())) return;
    const catId = page.getCatId();
    const lifecycle = getCategoryLifecycle(catId);
    if (!catId) {
      page.toast(page.messages.selectCategory, true);
      return;
    }

    await page.racePolling.loadRaceStatus();
    if (isRunning(catId)) {
      page.toast('Протокол уже запущен', true);
      return;
    }
    if (lifecycle.closed) {
      page.toast('Категория завершена', true);
      return;
    }
    if (isLockedByMassStart(catId)) {
      page.toast('Индивидуальный старт недоступен: категория уже запущена массовым стартом', true);
      return;
    }
    if (!page.state.spEntries.length) {
      page.toast('Протокол пуст', true);
      return;
    }

    const state = getState(catId);
    const isResume = lifecycle.started;
    const resumeDelayMs = isResume && state && state.pausedDelayMs ? state.pausedDelayMs : 0;

    await saveToServer();
    const confirmText =
      (isResume ? 'Продолжить' : 'Запустить') +
      ' стартовый протокол?' +
      (resumeDelayMs > 0
        ? '\nОчередь продолжится с оставшегося времени.'
        : '\nПервый оставшийся участник стартует сейчас.');
    if (!window.confirm(confirmText)) return;

    const payload = { category_id: parseInt(catId, 10) };
    if (resumeDelayMs > 0) payload.resume_delay_ms = resumeDelayMs;
    const result = await page.api.launchStartProtocol(payload);
    if (!result.ok) {
      page.toast(result.error || 'Ошибка запуска', true);
      return;
    }

    if (state) state.pausedDelayMs = null;
    await page.runPostActionSync({
      catId: catId,
      lifecyclePatch: { started: true, closed: false },
      syncProtocolStatus: true,
    });
    page.toast(isResume ? 'Протокол продолжен' : 'Протокол запущен');
  }

  async function stop() {
    if (!(await page.ensureJudgeAuth())) return;
    const catId = page.getCatId();
    if (!catId) return;

    const pausedDelayMs = computePausedDelayMs(catId);
    const result = await page.api.stopStartProtocol(catId);
    if (!result.ok) {
      page.toast(result.error || 'Ошибка остановки', true);
      return;
    }

    clearStateFor(catId);
    const state = getState(catId);
    state.pausedDelayMs = pausedDelayMs;
    await page.runPostActionSync({
      catId: catId,
      lifecyclePatch: { started: true, closed: false },
      syncProtocolStatus: true,
    });
    saveAllStates();
    page.toast('Протокол поставлен на паузу');
  }

  function updateCountdownDisplay(catId) {
    const state = page.state.spStates[catId];
    if (!state || !state.planned) return;

    let nextIdx = -1;
    for (let idx = 0; idx < state.planned.length; idx += 1) {
      if (!state.startedSet.has(state.planned[idx].rider_id)) {
        nextIdx = idx;
        break;
      }
    }

    if (nextIdx === -1) {
      page.els.spCountdownTimer.textContent = '00:00';
      page.els.spCountdownTimer.className = 'sp-countdown go';
      page.els.spNextInfo.textContent = 'Все стартовали';
      page.els.spNextInfo.dataset.nextKey = 'done';
      return;
    }

    const next = state.planned[nextIdx];
    let remain;
    if (state.running) remain = Math.max(0, (next.planned_time || 0) - Date.now());
    else if (state.pausedDelayMs !== null && state.pausedDelayMs !== undefined)
      remain = Math.max(0, state.pausedDelayMs);
    else return;

    const sec = remain > 0 ? Math.floor((remain + 999) / 1000) : 0;
    const minutes = Math.floor(sec / 60);
    const seconds = sec % 60;
    page.els.spCountdownTimer.textContent =
      String(minutes).padStart(2, '0') + ':' + String(seconds).padStart(2, '0');
    page.els.spCountdownTimer.className = 'sp-countdown' + (sec <= 3 ? ' go' : '');
    page.els.spNextInfo.dataset.nextKey = String(next.rider_id);
    page.els.spNextInfo.innerHTML =
      'Следующий: <b>#' + next.rider_number + '</b> ' + next.rider_name;
  }

  function ensureCountdownTick() {
    if (page.state.spCountdownTimer) return;
    page.state.spCountdownTimer = window.setInterval(function () {
      if (page.state.startMode !== 'individual') return;
      const catId = page.getCatId();
      if (catId) updateUI();
    }, page.constants.COUNTDOWN_TICK_MS);
  }

  function bind() {
    bindSearch();
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
    launch: launch,
    stop: stop,
    hasPendingEntries: hasPendingEntries,
    computePausedDelayMs: computePausedDelayMs,
    hasProtocolPlan: hasProtocolPlan,
    isLockedByMassStart: isLockedByMassStart,
  };
})();
