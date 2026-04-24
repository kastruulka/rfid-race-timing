(function () {
  const page = window.JudgePage || (window.JudgePage = {});

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
    ) {
      return;
    }

    const sharedProtocolTarget =
      page.state.startMode === 'individual' &&
      page.startProtocol &&
      page.startProtocol.getTargetCategoryIds
        ? {
            categoryIds: page.startProtocol.getTargetCategoryIds(),
            runMode: page.startProtocol.getRunMode ? page.startProtocol.getRunMode() : 'auto',
          }
        : null;
    const shouldStopSharedProtocol =
      sharedProtocolTarget &&
      sharedProtocolTarget.runMode === 'auto' &&
      sharedProtocolTarget.categoryIds.length > 1 &&
      sharedProtocolTarget.categoryIds.includes(String(catId));

    if (shouldStopSharedProtocol) {
      const stopResult = await page.api.stopStartProtocol({
        category_ids: sharedProtocolTarget.categoryIds.map(function (id) {
          return parseInt(id, 10);
        }),
      });
      if (!page.isResponseOk(stopResult)) {
        page.toast(
          page.getResponseError(
            stopResult,
            'Не удалось остановить общий протокол перед завершением категории'
          ),
          true
        );
        return;
      }
    }

    const result = await page.api.finishRace(catId);
    if (result.ok && shouldStopSharedProtocol) {
      const clearResult = await page.api.clearStartProtocol({
        category_ids: sharedProtocolTarget.categoryIds.map(function (id) {
          return parseInt(id, 10);
        }),
      });
      if (!page.isResponseOk(clearResult)) {
        page.toast(
          page.getResponseError(
            clearResult,
            'Не удалось очистить общий протокол после завершения категории'
          ),
          true
        );
        return;
      }
      page.startProtocol.clearStateFor(sharedProtocolTarget.categoryIds);
    }
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
    ) {
      return;
    }
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
    ) {
      return;
    }
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
    page.els.btnMassStart.addEventListener('click', page.massStart.doMassStart);
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
        page.massStart.updateControls();
      });
    }
    if (page.els.massStartCategoryList) {
      page.els.massStartCategoryList.addEventListener('change', function () {
        page.massStart.saveSelectedIds(page.massStart.getSelectedIds());
        page.massStart.updateControls();
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

  function initJudgeActionsLayer() {
    page.actions = {
      loadLog: function loadLog() {
        return page.logNotes.loadLog();
      },
      loadNotes: function loadNotes() {
        return page.logNotes.loadNotes();
      },
    };
  }

  page.judgeActions = {
    init: initJudgeActionsLayer,
    setStartMode: setStartMode,
    doIndividualStart: doIndividualStart,
    doUnfinishRider: doUnfinishRider,
    doEditFinishTime: doEditFinishTime,
    doDNF: doDNF,
    doDSQ: doDSQ,
    doTimePenalty: doTimePenalty,
    doExtraLap: doExtraLap,
    doWarning: doWarning,
    doFinishRace: doFinishRace,
    doResetCategory: doResetCategory,
    doNewRace: doNewRace,
    bindActionButtons: bindActionButtons,
    bindSubmitShortcuts: bindSubmitShortcuts,
  };
})();
