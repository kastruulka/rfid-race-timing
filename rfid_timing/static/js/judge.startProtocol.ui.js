(function () {
  const page = window.JudgePage || (window.JudgePage = {});

  function renderCategoryOptions(params) {
    const listEl = params.listEl;
    const categoryNames = params.categoryNames || {};
    const selectedIds = new Set(
      (
        params.getStoredSelectedIds ||
        function () {
          return [];
        }
      )()
    );

    if (!listEl) return;
    listEl.innerHTML = '';

    Object.keys(categoryNames).forEach(function (catId) {
      const option = document.createElement('label');
      option.className = 'mass-start-check';

      const input = document.createElement('input');
      input.type = 'checkbox';
      input.value = catId;
      input.checked = selectedIds.has(String(catId));

      const text = document.createElement('span');
      text.textContent = categoryNames[catId];

      option.appendChild(input);
      option.appendChild(text);
      listEl.appendChild(option);
    });
  }

  function updateScopeUI(params) {
    if (!params.selectedWrapEl) return;
    params.selectedWrapEl.style.display = params.getScope() === 'selected' ? 'block' : 'none';
  }

  function renderEmptyState(params) {
    params.listEl.innerHTML = '';
    const empty = document.createElement('div');
    empty.className = 'sp-empty';
    empty.textContent = params.text;
    params.listEl.appendChild(empty);
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

  function drop(event, params) {
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
    params.renderList();
    params.saveToServer();
  }

  function renderList(params) {
    const target = params.getTarget();
    const state = target.key ? params.getState(target.key, target.categoryIds) : null;
    const interval =
      parseInt(page.els.spInterval.value, 10) || page.constants.START_PROTOCOL_INTERVAL_SEC;
    const startedSet = state ? state.startedSet : new Set();
    const running = target.key ? params.isRunning(target.key) : false;

    page.els.spList.innerHTML = '';
    if (!target.categoryIds.length) {
      params.renderEmptyState({
        listEl: page.els.spList,
        text: 'Выберите категории, чтобы собрать очередь индивидуального старта',
      });
      return;
    }
    if (!page.state.spEntries.length) {
      params.renderEmptyState({
        listEl: page.els.spList,
        text: 'Протокол пуст. Используйте Авто или добавьте участников вручную.',
      });
      return;
    }

    page.state.spEntries.forEach(function (entry, index) {
      const offsetSec = index * interval;
      const minutes = Math.floor(offsetSec / 60);
      const seconds = offsetSec % 60;
      const timeStr =
        minutes > 0 ? minutes + ':' + String(seconds).padStart(2, '0') : seconds + 'с';
      const isStarted = startedSet.has(entry.rider_id) || String(entry.status || '') === 'STARTED';
      const isNext =
        running &&
        !isStarted &&
        params.isPendingProtocolEntry(entry) &&
        state &&
        Array.isArray(state.planned)
          ? state.planned.findIndex(function (plannedEntry) {
              return (
                params.isPendingProtocolEntry(plannedEntry) &&
                !state.startedSet.has(plannedEntry.rider_id)
              );
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
      row.addEventListener('drop', function (event) {
        drop(event, params);
      });

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
      } else if (String(entry.status || '') === 'ERROR') {
        const error = document.createElement('span');
        error.style.color = 'var(--red)';
        error.style.fontSize = '10px';
        error.style.fontWeight = '700';
        error.textContent = 'ERR';
        row.appendChild(error);
      } else if (canEdit) {
        const del = document.createElement('span');
        del.className = 'sp-del';
        del.dataset.action = 'remove-sp-entry';
        del.dataset.index = String(index);
        del.textContent = 'X';
        row.appendChild(del);
      } else {
        const spacer = document.createElement('span');
        spacer.className = 'sp-del';
        spacer.style.visibility = 'hidden';
        spacer.textContent = 'X';
        row.appendChild(spacer);
      }

      page.els.spList.appendChild(row);
    });
  }

  function updateCountdownDisplay(params) {
    const target = params.target;
    const state = page.state.spStates[target.key];
    if (!state || !Array.isArray(state.planned)) return;
    const next = state.planned.find(function (entry) {
      return params.isPendingProtocolEntry(entry) && !state.startedSet.has(entry.rider_id);
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
      'Следующий: #' +
      next.rider_number +
      '</b> ' +
      next.rider_name +
      (target.isMulti && next.category_name ? ' [' + next.category_name + ']' : '');
  }

  function updateUI(params) {
    params.updateScopeUI();
    const target = params.getTarget();
    const state = target.key ? params.getState(target.key, target.categoryIds) : null;
    const runMode = params.getRunMode();
    const running = target.key ? params.isRunning(target.key) : false;
    const pending = target.key ? params.hasPendingEntries(target.key) : false;
    const hasCategories = target.categoryIds.length > 0;
    const hasLockedOnly =
      hasCategories &&
      target.categoryIds.every(function (catId) {
        return params.isLockedByMassStart(catId);
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
        return params.getCategoryLifecycle(catId).started;
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
    params.updateCountdownDisplay(target);
  }

  page.startProtocolUi = {
    renderCategoryOptions: renderCategoryOptions,
    updateScopeUI: updateScopeUI,
    renderEmptyState: renderEmptyState,
    renderList: renderList,
    updateCountdownDisplay: updateCountdownDisplay,
    updateUI: updateUI,
  };
})();
