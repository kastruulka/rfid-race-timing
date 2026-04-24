(function () {
  const page = window.JudgePage || (window.JudgePage = {});
  const helpers = page.judgeActionHelpers;

  async function doIndividualStart() {
    if (!(await helpers.ensureActionAuth())) return;
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

    const label = helpers.getSelectedRiderLabel();
    if (!window.confirm('Дать индивидуальный старт участнику ' + label + '?')) return;

    await helpers.runApiAction({
      run: function () {
        return page.api.individualStart(page.state.selectedRiderId);
      },
      errorMessage: 'Ошибка старта',
      onSuccess: async function (result) {
        const data = page.getResponseData(result) || {};
        page.toast('Старт: ' + (((data || {}).info || {}).rider_name || label));
        await page.runPostActionSync({
          catId: page.getCatId(),
          lifecyclePatch: { started: true, closed: false },
          refreshRiderPanel: true,
        });
      },
    });
  }

  async function doUnfinishRider() {
    if (!(await helpers.ensureActionAuth())) return;
    if (!helpers.ensureSelectedRider()) return;
    const label = helpers.getSelectedRiderLabel();
    if (!window.confirm('Отменить финиш ' + label + '?\nУчастник вернётся в статус RACING.')) {
      return;
    }
    await helpers.runApiAction({
      requireRider: true,
      run: function () {
        return page.api.unfinishRider(page.state.selectedRiderId);
      },
      errorMessage: 'Ошибка',
      onSuccess: async function () {
        page.toast('Финиш отменён: ' + label);
        await page.riderPanel.refreshRiderPanel();
        await page.racePolling.loadRaceStatus();
      },
    });
  }

  async function doEditFinishTime() {
    if (!(await helpers.ensureActionAuth())) return;
    if (!helpers.ensureSelectedRider()) return;

    const minutes = parseInt(page.els.editFinishMm.value.trim(), 10) || 0;
    const seconds = parseFloat(page.els.editFinishSs.value.trim()) || 0;
    if (minutes < 0 || seconds < 0 || seconds >= 60) {
      page.toast('Неверный формат времени', true);
      return;
    }

    const totalMs = Math.round((minutes * 60 + seconds) * 1000);
    const label = helpers.getSelectedRiderLabel();
    const timeStr = String(minutes).padStart(2, '0') + ':' + seconds.toFixed(1).padStart(4, '0');
    if (!window.confirm('Изменить время финиша ' + label + ' на ' + timeStr + '?')) return;

    await helpers.runApiAction({
      requireRider: true,
      run: function () {
        return page.api.editFinishTime(page.state.selectedRiderId, totalMs);
      },
      errorMessage: 'Ошибка',
      onSuccess: async function () {
        page.toast('Время финиша изменено: ' + label + ' -> ' + timeStr);
        page.els.editFinishMm.value = '';
        page.els.editFinishSs.value = '';
        await page.riderPanel.refreshRiderPanel();
        await page.racePolling.loadRaceStatus();
      },
    });
  }

  async function doDNF(reason) {
    await helpers.runApiAction({
      requireRider: true,
      run: function () {
        return page.api.dnf(page.state.selectedRiderId, reason);
      },
      errorMessage: 'Ошибка',
      onSuccess: async function () {
        page.toast('DNF зафиксирован');
        await page.logNotes.loadLog();
        await page.riderPanel.refreshRiderPanel();
      },
    });
  }

  async function doDSQ() {
    await helpers.runApiAction({
      requireRider: true,
      run: function () {
        return page.api.dsq(page.state.selectedRiderId, page.els.dsqReason.value.trim());
      },
      errorMessage: 'Ошибка',
      onSuccess: async function () {
        page.toast('DSQ — дисквалификация');
        page.els.dsqReason.value = '';
        await page.logNotes.loadLog();
        await page.riderPanel.refreshRiderPanel();
      },
    });
  }

  async function doTimePenalty() {
    const seconds = parseFloat(page.els.penSeconds.value) || 0;
    if (seconds <= 0) {
      page.toast('Укажите время штрафа', true);
      return;
    }
    await helpers.runApiAction({
      requireRider: true,
      run: function () {
        return page.api.timePenalty(
          page.state.selectedRiderId,
          seconds,
          page.els.penReason.value.trim()
        );
      },
      errorMessage: 'Ошибка',
      onSuccess: async function () {
        page.toast('+' + seconds + ' сек штрафа');
        page.els.penReason.value = '';
        await page.logNotes.loadLog();
        await page.riderPanel.refreshRiderPanel();
        await page.racePolling.loadRaceStatus();
      },
    });
  }

  async function doExtraLap() {
    const laps = parseInt(page.els.extraLaps.value, 10) || 1;
    await helpers.runApiAction({
      requireRider: true,
      run: function () {
        return page.api.extraLap(
          page.state.selectedRiderId,
          laps,
          page.els.extraReason.value.trim()
        );
      },
      errorMessage: 'Ошибка',
      onSuccess: async function () {
        page.toast('+' + laps + ' штрафной круг');
        page.els.extraReason.value = '';
        await page.logNotes.loadLog();
      },
    });
  }

  async function doWarning() {
    await helpers.runApiAction({
      requireRider: true,
      run: function () {
        return page.api.warning(page.state.selectedRiderId, page.els.warnReason.value.trim());
      },
      errorMessage: 'Ошибка',
      onSuccess: async function () {
        page.toast('Предупреждение выдано');
        page.els.warnReason.value = '';
        await page.logNotes.loadLog();
      },
    });
  }

  page.judgeRiderActions = {
    doDNF: doDNF,
    doDSQ: doDSQ,
    doEditFinishTime: doEditFinishTime,
    doExtraLap: doExtraLap,
    doIndividualStart: doIndividualStart,
    doTimePenalty: doTimePenalty,
    doUnfinishRider: doUnfinishRider,
    doWarning: doWarning,
  };
})();
