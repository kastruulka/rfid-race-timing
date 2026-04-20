(function () {
  const page = window.JudgePage || (window.JudgePage = {});

  if (!page.state.categoryLifecycleById) page.state.categoryLifecycleById = {};
  if (!page.state.categoryLifecycleOverrides) page.state.categoryLifecycleOverrides = {};

  function getDefaultCategoryLifecycle() {
    return { started: false, closed: false };
  }

  function pruneCategoryLifecycleOverrides() {
    Object.keys(page.state.categoryLifecycleOverrides).forEach(function (catId) {
      const override = page.state.categoryLifecycleOverrides[catId];
      const serverState = page.state.categoryLifecycleById[catId] || getDefaultCategoryLifecycle();
      const startedMatches =
        override.started === undefined || override.started === serverState.started;
      const closedMatches = override.closed === undefined || override.closed === serverState.closed;
      if (startedMatches && closedMatches) {
        delete page.state.categoryLifecycleOverrides[catId];
      }
    });
  }

  page.getCategoryLifecycle = function getCategoryLifecycle(catId) {
    const key = String(catId || '');
    const serverState = page.state.categoryLifecycleById[key] || getDefaultCategoryLifecycle();
    const override = page.state.categoryLifecycleOverrides[key] || {};
    return {
      started: override.started !== undefined ? override.started : serverState.started,
      closed: override.closed !== undefined ? override.closed : serverState.closed,
    };
  };

  page.setCategoryLifecycleOverride = function setCategoryLifecycleOverride(catId, patch) {
    if (!catId) return;
    const key = String(catId);
    const prev = page.state.categoryLifecycleOverrides[key] || {};
    page.state.categoryLifecycleOverrides[key] = Object.assign({}, prev, patch || {});
  };

  page.clearCategoryLifecycleOverride = function clearCategoryLifecycleOverride(catId) {
    if (!catId) return;
    delete page.state.categoryLifecycleOverrides[String(catId)];
  };

  page.replaceCategoryLifecycleState = function replaceCategoryLifecycleState(nextState) {
    page.state.categoryLifecycleById = Object.assign({}, nextState || {});
    pruneCategoryLifecycleOverrides();
  };

  page.syncCurrentCategoryLifecycle = function syncCurrentCategoryLifecycle(catId) {
    const lifecycle = page.getCategoryLifecycle(catId);
    page.state.currentCategoryStarted = lifecycle.started;
    page.state.currentCategoryClosed = lifecycle.closed;
    return lifecycle;
  };

  page.runPostActionSync = async function runPostActionSync(options) {
    const opts = Object.assign(
      {
        catId: page.getCatId(),
        lifecyclePatch: null,
        syncProtocolStatus: false,
        clearProtocolState: false,
        clearProtocolEntries: false,
        markTimerClosed: null,
        clearTimer: false,
        updateTimers: false,
        refreshRaceStatus: true,
        refreshRiderPanel: false,
        refreshLog: false,
        refreshNotes: false,
      },
      options || {}
    );

    if (opts.catId && opts.lifecyclePatch) {
      page.setCategoryLifecycleOverride(opts.catId, opts.lifecyclePatch);
      page.syncCurrentCategoryLifecycle(opts.catId);
    }

    if (opts.clearProtocolState && opts.catId) {
      page.startProtocol.clearStateFor(opts.catId);
    }

    if (opts.clearProtocolEntries) {
      page.state.spEntries = [];
      page.startProtocol.renderList();
    }

    if (opts.catId && opts.markTimerClosed !== null) {
      page.state.catTimerClosed[opts.catId] = !!opts.markTimerClosed;
    }

    if (opts.clearTimer && opts.catId) {
      delete page.state.catTimerElapsed[opts.catId];
      delete page.state.catTimerPerf[opts.catId];
      delete page.state.catTimerClosed[opts.catId];
    }

    if (opts.syncProtocolStatus && opts.catId) {
      await page.startProtocol.syncStatus(opts.catId, true);
    }

    page.startProtocol.updateUI();

    if (opts.updateTimers) {
      page.racePolling.updateCategoryTimers();
    }

    if (opts.refreshRaceStatus) {
      await page.racePolling.loadRaceStatus();
    }

    if (opts.refreshRiderPanel) {
      await page.riderPanel.refreshRiderPanel();
    }

    if (opts.refreshLog) {
      await page.logNotes.loadLog();
    }

    if (opts.refreshNotes) {
      await page.logNotes.loadNotes();
    }
  };

  function getStoredMassStartSelectedIds() {
    const raw = sessionStorage.getItem('judge_mass_start_selected') || '';
    return raw
      .split(',')
      .map(function (value) {
        return value.trim();
      })
      .filter(Boolean);
  }

  function saveMassStartSelectedIds(ids) {
    sessionStorage.setItem('judge_mass_start_selected', (ids || []).join(','));
  }

  function getMassStartScope() {
    return page.els.massStartScope ? page.els.massStartScope.value : 'current';
  }

  function getSelectedMassStartCategoryIds() {
    if (!page.els.massStartCategoryList) return [];
    return Array.from(
      page.els.massStartCategoryList.querySelectorAll('input[type="checkbox"]:checked')
    ).map(function (input) {
      return String(input.value);
    });
  }

  function getAllCategoryIds() {
    return Array.from(page.els.raceCategory.querySelectorAll('option'))
      .map(function (option) {
        return String(option.value || '');
      })
      .filter(Boolean);
  }

  function getMassStartTargetCategoryIds() {
    const scope = getMassStartScope();
    if (scope === 'all') return getAllCategoryIds();
    if (scope === 'selected') return getSelectedMassStartCategoryIds();
    const currentId = page.getCatId();
    return currentId ? [String(currentId)] : [];
  }

  function getMassStartTargetSummary(targetIds) {
    const all = (targetIds || []).filter(Boolean);
    const active = all.filter(function (catId) {
      const lifecycle = page.getCategoryLifecycle(catId);
      return !lifecycle.started && !lifecycle.closed;
    });
    return { all: all, active: active };
  }

  function getMassStartButtonLabel(summary) {
    if (!summary.all.length) return 'Выберите категории';
    if (!summary.active.length) return 'Старт недоступен';
    if (summary.active.length === 1) return '▶ Масс-старт';
    return '▶ Масс-старт x' + summary.active.length;
  }

  function updateMassStartScopeUI() {
    if (!page.els.massStartSelectedWrap) return;
    page.els.massStartSelectedWrap.style.display =
      getMassStartScope() === 'selected' ? 'block' : 'none';
  }

  function renderMassStartCategoryOptions() {
    if (!page.els.massStartCategoryList) return;
    const selectedIds = new Set(getStoredMassStartSelectedIds());
    page.els.massStartCategoryList.innerHTML = '';

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
      page.els.massStartCategoryList.appendChild(option);
    });
  }

  function updateMassStartControls() {
    updateMassStartScopeUI();
    const summary = getMassStartTargetSummary(getMassStartTargetCategoryIds());
    page.setStateDisabled(page.els.btnMassStart, !summary.active.length);
    page.els.btnMassStart.textContent = getMassStartButtonLabel(summary);
  }

  page.renderMassStartCategoryOptions = renderMassStartCategoryOptions;
  page.updateMassStartControls = updateMassStartControls;

  function setStartMode(mode) {
    page.state.startMode = mode;
    sessionStorage.setItem('judge_start_mode', mode);
    page.els.raceControl.dataset.startMode = mode;
    if (mode === 'mass') {
      page.els.btnModeMass.style.background = 'var(--accent)';
      page.els.btnModeMass.style.color = 'var(--bg)';
      page.els.btnModeIndividual.style.background = 'transparent';
      page.els.btnModeIndividual.style.color = 'var(--text-dim)';
      page.els.massStartSection.style.display = 'block';
      page.els.individualStartSection.style.display = 'none';
      return;
    }
    page.els.btnModeIndividual.style.background = 'var(--accent)';
    page.els.btnModeIndividual.style.color = 'var(--bg)';
    page.els.btnModeMass.style.background = 'transparent';
    page.els.btnModeMass.style.color = 'var(--text-dim)';
    page.els.massStartSection.style.display = 'none';
    page.els.individualStartSection.style.display = 'block';
    page.startProtocol.switchToCategory();
  }

  async function doMassStart() {
    if (!(await page.ensureJudgeAuth())) return;
    if (page.els.btnMassStart.disabled) {
      page.toast(page.els.btnMassStart.textContent || 'Старт уже недоступен', true);
      return;
    }
    const summary = getMassStartTargetSummary(getMassStartTargetCategoryIds());
    if (summary.all.length) {
      if (!summary.active.length) {
        page.toast('Для старта не осталось доступных категорий', true);
        return;
      }
      const targetNames = summary.active.map(function (catId) {
        return page.categoryNames[String(catId)] || String(catId);
      });
      const confirmText =
        targetNames.length === 1
          ? 'Запустить масс-старт для категории "' + targetNames[0] + '"?'
          : 'Запустить масс-старт для категорий:\n• ' + targetNames.join('\n• ');
      if (!window.confirm(confirmText)) return;

      const payload =
        summary.active.length === 1
          ? { category_id: parseInt(summary.active[0], 10) }
          : {
              category_ids: summary.active.map(function (catId) {
                return parseInt(catId, 10);
              }),
            };

      const result = await page.api.massStart(payload);
      if (page.isResponseOk(result)) {
        const data = page.getResponseData(result) || {};
        summary.active.forEach(function (catId) {
          page.setCategoryLifecycleOverride(catId, { started: true, closed: false });
        });
        page.syncCurrentCategoryLifecycle(page.getCatId());
        updateMassStartControls();
        page.toast('Масс-старт! Участников: ' + (((data || {}).info || {}).riders_started || '?'));
        await page.racePolling.loadRaceStatus();
        return;
      }
      page.toast(page.getResponseError(result, 'Ошибка старта'), true);
      return;
    }
    if (getMassStartScope() !== 'current') {
      page.toast('Выберите категории для старта', true);
      return;
    }
    const catId = page.getCatId();
    if (!catId) {
      page.toast(page.messages.selectCategory, true);
      return;
    }
    if (!window.confirm('Запустить масс-старт для выбранной категории?')) return;
    const result = await page.api.massStart(catId);
    if (result.ok) {
      page.toast('Масс-старт! Участников: ' + (((result || {}).info || {}).riders_started || '?'));
      await page.runPostActionSync({
        catId: catId,
        lifecyclePatch: { started: true, closed: false },
      });
      return;
    }
    page.toast(result.error || 'Ошибка', true);
  }

  async function doIndividualStart() {
    if (!(await page.ensureJudgeAuth())) return;
    if (page.els.btnIndividualStart.disabled) {
      page.toast(
        page.els.btnIndividualStart.textContent || 'Индивидуальный старт сейчас недоступен',
        true
      );
      return;
    }
    if (!page.ensureProtocolCategory()) return;
    if (page.startProtocol.isLockedByMassStart(page.getCatId())) {
      page.toast('Индивидуальный старт недоступен: категория уже запущена массовым стартом', true);
      return;
    }
    if (!page.state.selectedRiderId) {
      page.toast('Выберите участника для старта', true);
      return;
    }

    const rider = page.state.riders.find(function (entry) {
      return entry.id === page.state.selectedRiderId;
    });
    const label = rider
      ? '#' + rider.number + ' ' + rider.last_name
      : '#' + page.state.selectedRiderId;
    if (!window.confirm('Дать индивидуальный старт участнику ' + label + '?')) return;

    const result = await page.api.individualStart(page.state.selectedRiderId);
    if (page.isResponseOk(result)) {
      const data = page.getResponseData(result) || {};
      page.toast('Старт: ' + (((data || {}).info || {}).rider_name || label));
      await page.runPostActionSync({
        catId: page.getCatId(),
        lifecyclePatch: { started: true, closed: false },
        refreshRiderPanel: true,
      });
      return;
    }
    page.toast(page.getResponseError(result, 'Ошибка старта'), true);
  }

  async function doUnfinishRider() {
    if (!(await page.ensureJudgeAuth())) return;
    if (!page.requireRider()) return;
    const rider = page.state.riders.find(function (entry) {
      return entry.id === page.state.selectedRiderId;
    });
    const label = rider
      ? '#' + rider.number + ' ' + rider.last_name
      : '#' + page.state.selectedRiderId;
    if (!window.confirm('Отменить финиш ' + label + '?\nУчастник вернётся в статус RACING.'))
      return;
    const result = await page.api.unfinishRider(page.state.selectedRiderId);
    if (result.ok) {
      page.toast('Финиш отменён: ' + label);
      await page.riderPanel.refreshRiderPanel();
      await page.racePolling.loadRaceStatus();
      return;
    }
    page.toast(result.error || 'Ошибка', true);
  }

  async function doEditFinishTime() {
    if (!(await page.ensureJudgeAuth())) return;
    if (!page.requireRider()) return;

    const minutes = parseInt(page.els.editFinishMm.value.trim(), 10) || 0;
    const seconds = parseFloat(page.els.editFinishSs.value.trim()) || 0;
    if (minutes < 0 || seconds < 0 || seconds >= 60) {
      page.toast('Неверный формат времени', true);
      return;
    }

    const totalMs = Math.round((minutes * 60 + seconds) * 1000);
    const rider = page.state.riders.find(function (entry) {
      return entry.id === page.state.selectedRiderId;
    });
    const label = rider
      ? '#' + rider.number + ' ' + rider.last_name
      : '#' + page.state.selectedRiderId;
    const timeStr = String(minutes).padStart(2, '0') + ':' + seconds.toFixed(1).padStart(4, '0');
    if (!window.confirm('Изменить время финиша ' + label + ' на ' + timeStr + '?')) return;

    const result = await page.api.editFinishTime(page.state.selectedRiderId, totalMs);
    if (result.ok) {
      page.toast('Время финиша изменено: ' + label + ' -> ' + timeStr);
      page.els.editFinishMm.value = '';
      page.els.editFinishSs.value = '';
      await page.riderPanel.refreshRiderPanel();
      await page.racePolling.loadRaceStatus();
      return;
    }
    page.toast(result.error || 'Ошибка', true);
  }

  async function doDNF(reason) {
    if (!(await page.ensureJudgeAuth())) return;
    if (!page.requireRider()) return;
    const result = await page.api.dnf(page.state.selectedRiderId, reason);
    if (result.ok) {
      page.toast('DNF зафиксирован');
      page.logNotes.loadLog();
      page.riderPanel.refreshRiderPanel();
      return;
    }
    page.toast(result.error || 'Ошибка', true);
  }

  async function doDSQ() {
    if (!(await page.ensureJudgeAuth())) return;
    if (!page.requireRider()) return;
    const result = await page.api.dsq(page.state.selectedRiderId, page.els.dsqReason.value.trim());
    if (result.ok) {
      page.toast('DSQ — дисквалификация');
      page.els.dsqReason.value = '';
      page.logNotes.loadLog();
      page.riderPanel.refreshRiderPanel();
      return;
    }
    page.toast(result.error || 'Ошибка', true);
  }

  async function doTimePenalty() {
    if (!(await page.ensureJudgeAuth())) return;
    if (!page.requireRider()) return;
    const seconds = parseFloat(page.els.penSeconds.value) || 0;
    if (seconds <= 0) {
      page.toast('Укажите время штрафа', true);
      return;
    }
    const result = await page.api.timePenalty(
      page.state.selectedRiderId,
      seconds,
      page.els.penReason.value.trim()
    );
    if (result.ok) {
      page.toast('+' + seconds + ' сек штрафа');
      page.els.penReason.value = '';
      page.logNotes.loadLog();
      await page.riderPanel.refreshRiderPanel();
      await page.racePolling.loadRaceStatus();
      return;
    }
    page.toast(result.error || 'Ошибка', true);
  }

  async function doExtraLap() {
    if (!(await page.ensureJudgeAuth())) return;
    if (!page.requireRider()) return;
    const laps = parseInt(page.els.extraLaps.value, 10) || 1;
    const result = await page.api.extraLap(
      page.state.selectedRiderId,
      laps,
      page.els.extraReason.value.trim()
    );
    if (result.ok) {
      page.toast('+' + laps + ' штрафной круг');
      page.els.extraReason.value = '';
      page.logNotes.loadLog();
      return;
    }
    page.toast(result.error || 'Ошибка', true);
  }

  async function doWarning() {
    if (!(await page.ensureJudgeAuth())) return;
    if (!page.requireRider()) return;
    const result = await page.api.warning(
      page.state.selectedRiderId,
      page.els.warnReason.value.trim()
    );
    if (result.ok) {
      page.toast('Предупреждение выдано');
      page.els.warnReason.value = '';
      page.logNotes.loadLog();
      return;
    }
    page.toast(result.error || 'Ошибка', true);
  }

  async function doFinishRace() {
    if (!(await page.ensureJudgeAuth())) return;
    const catId = page.getCatId();
    if (!catId) {
      page.toast(page.messages.selectCategory, true);
      return;
    }
    const catName = page.categoryNames[catId] || catId;
    if (
      !window.confirm(
        'Завершить категорию «' +
          catName +
          '»?\n* Участники, проехавшие все круги -> FINISHED\n* Остальные -> DNF\n* Таймер категории остановится'
      )
    )
      return;
    const result = await page.api.finishRace(catId);
    if (result.ok) {
      page.toast(
        'Категория завершена. Финиш: ' +
          (result.finished || 0) +
          ', DNF: ' +
          (result.dnf_count || 0)
      );
      await page.runPostActionSync({
        catId: catId,
        lifecyclePatch: { started: false, closed: true },
        clearProtocolState: true,
        clearProtocolEntries: String(page.getCatId()) === String(catId),
        markTimerClosed: true,
        updateTimers: true,
        refreshLog: true,
      });
      return;
    }
    page.toast(result.error || 'Ошибка', true);
  }

  async function doResetCategory() {
    if (!(await page.ensureJudgeAuth())) return;
    const catId = page.getCatId();
    if (!catId) {
      page.toast('Выберите категорию для сброса', true);
      return;
    }
    const catName = page.categoryNames[catId] || catId;
    if (
      !window.confirm(
        'Сбросить категорию «' +
          catName +
          '»?\n\nВсе результаты, круги и штрафы этой категории будут удалены.\nУчастники останутся в стартовом листе.\nДругие категории не затрагиваются.'
      )
    )
      return;
    const result = await page.api.resetCategory(catId);
    if (result.ok) {
      page.toast(
        'Категория «' +
          (result.category || catName) +
          '» сброшена: ' +
          (result.deleted_results || 0) +
          ' результатов удалено'
      );
      await page.runPostActionSync({
        catId: catId,
        lifecyclePatch: { started: false, closed: false },
        clearProtocolState: true,
        clearProtocolEntries: true,
        clearTimer: true,
        updateTimers: true,
        refreshLog: true,
        refreshNotes: true,
      });
      return;
    }
    page.toast(result.error || 'Ошибка', true);
  }

  async function doNewRace() {
    if (!(await page.ensureJudgeAuth())) return;
    if (
      !window.confirm(
        'Создать полностью новую гоночную сессию?\nРезультаты ВСЕХ категорий будут архивированы.\n\nДля сброса одной категории используйте «Сбросить категорию».'
      )
    )
      return;
    const result = await page.api.newRace();
    if (result.ok) {
      page.toast('Новая сессия #' + result.race_id);
      page.replaceCategoryLifecycleState({});
      page.state.categoryLifecycleOverrides = {};
      page.syncCurrentCategoryLifecycle(page.getCatId());
      Object.keys(page.state.spStates).forEach(function (cid) {
        page.startProtocol.clearStateFor(cid);
      });
      page.state.spEntries = [];
      page.startProtocol.renderList();
      page.state.catTimerElapsed = {};
      page.state.catTimerPerf = {};
      page.state.catTimerClosed = {};
      page.startProtocol.updateUI();
      await Promise.all([
        page.racePolling.loadRaceStatus(),
        page.logNotes.loadLog(),
        page.logNotes.loadNotes(),
      ]);
      return;
    }
    page.toast(result.error || 'Ошибка', true);
  }

  function bindActionButtons() {
    page.els.btnModeMass.addEventListener('click', function () {
      setStartMode('mass');
    });
    page.els.btnModeIndividual.addEventListener('click', function () {
      setStartMode('individual');
    });
    page.els.btnMassStart.addEventListener('click', doMassStart);
    page.els.btnFinishRace.addEventListener('click', doFinishRace);
    page.els.btnSpAutoFill.addEventListener('click', page.startProtocol.autoFill);
    page.els.btnSpClear.addEventListener('click', page.startProtocol.clear);
    page.els.btnSpLaunch.addEventListener('click', page.startProtocol.launch);
    page.els.btnSpStop.addEventListener('click', page.startProtocol.stop);
    page.els.btnFinishRaceInd.addEventListener('click', doFinishRace);
    page.els.btnIndividualStart.addEventListener('click', doIndividualStart);
    page.els.btnResetCat.addEventListener('click', doResetCategory);
    page.els.btnNewRace.addEventListener('click', doNewRace);
    page.els.btnAddManualLap.addEventListener('click', page.riderPanel.doAddManualLap);
    page.els.btnEditFinishTime.addEventListener('click', doEditFinishTime);
    page.els.btnUnfinishRider.addEventListener('click', doUnfinishRider);
    page.els.btnDnfVoluntary.addEventListener('click', function () {
      doDNF('voluntary');
    });
    page.els.btnDnfMechanical.addEventListener('click', function () {
      doDNF('mechanical');
    });
    page.els.btnDnfInjury.addEventListener('click', function () {
      doDNF('injury');
    });
    page.els.btnTimePenalty.addEventListener('click', doTimePenalty);
    page.els.btnDsq.addEventListener('click', doDSQ);
    page.els.btnExtraLap.addEventListener('click', doExtraLap);
    page.els.btnWarning.addEventListener('click', doWarning);
    page.els.btnAddNote.addEventListener('click', page.logNotes.addNote);
    if (page.els.massStartScope) {
      page.els.massStartScope.addEventListener('change', function () {
        sessionStorage.setItem('judge_mass_start_scope', this.value);
        updateMassStartControls();
      });
    }
    if (page.els.massStartCategoryList) {
      page.els.massStartCategoryList.addEventListener('change', function () {
        saveMassStartSelectedIds(getSelectedMassStartCategoryIds());
        updateMassStartControls();
      });
    }
  }

  function bindSubmitShortcuts() {
    [
      [page.els.penReason, doTimePenalty],
      [page.els.dsqReason, doDSQ],
      [page.els.extraReason, doExtraLap],
      [page.els.warnReason, doWarning],
    ].forEach(function (entry) {
      const input = entry[0];
      const handler = entry[1];
      input.addEventListener('keydown', function (event) {
        if (event.key !== 'Enter') return;
        event.preventDefault();
        handler();
      });
    });
  }

  function bind() {
    bindActionButtons();
    bindSubmitShortcuts();
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
      updateMassStartControls();
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
      if (savedProtocolRunMode && page.els.spRunMode)
        page.els.spRunMode.value = savedProtocolRunMode;
      updateMassStartScopeUI();
      if (page.startProtocol.updateScopeUI) page.startProtocol.updateScopeUI();
      if (savedMode === 'individual') setStartMode('individual');
      if (savedMode === 'individual') page.startProtocol.updateUI();
      updateMassStartControls();

      page.racePolling.startTimerTick();
      page.startProtocol.ensureCountdownTick();
      page.racePolling.startPolling();
      document.addEventListener('visibilitychange', handleVisibilityChange);
      window.addEventListener('beforeunload', destroy);
    } finally {
      window.pageHydration.finish();
    }
  }

  page.actions = {
    loadLog: page.logNotes.loadLog,
    loadNotes: page.logNotes.loadNotes,
  };
  page.destroy = destroy;

  init();
})();
