(function () {
  const page = window.JudgePage || (window.JudgePage = {});

  function bindSearch(params) {
    page.state.spDropdown = page.createRiderDropdown({
      inputEl: page.els.spSearch,
      listEl: page.els.spDropdown,
      source: function () {
        if (!params.getTargetCategoryIds().length) return [];
        const query = String(page.els.spSearch.value || '').toLowerCase();
        return params.getAvailableRiders().filter(function (rider) {
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
        const targetIds = params.getTargetCategoryIds();
        if (!targetIds.length) return 'Сначала выберите категории';
        return params.getAvailableRiders().length === 0
          ? 'Все участники уже в протоколе'
          : 'Не найдено';
      },
      onSelect: function (rider) {
        selectFromSearch(params, rider.id);
      },
    });
  }

  function selectFromSearch(params, riderId) {
    if (!page.requireJudgeEditAccess()) return;
    const targetIds = params.getTargetCategoryIds();
    if (!targetIds.length) {
      page.toast('Сначала выберите категории для индивидуального старта', true);
      return;
    }
    const rider = page.state.riders.find(function (entry) {
      return entry.id === riderId;
    });
    if (!rider) return;
    if (params.isLockedByMassStart(rider.category_id)) {
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
    params.renderList();
    params.saveToServer();
    page.toast('#' + rider.number + ' ' + (rider.last_name || '') + ' добавлен');
  }

  function removeEntry(params, index) {
    if (!page.requireJudgeEditAccess()) return;
    const target = params.getTarget();
    if (target.key && params.isRunning(target.key)) {
      page.toast('Поставьте протокол на паузу перед удалением участника из очереди', true);
      return;
    }
    const state = target.key ? params.getState(target.key, target.categoryIds) : null;
    const entry = page.state.spEntries[index];
    if (entry && state && state.startedSet && state.startedSet.has(entry.rider_id)) {
      page.toast('Уже стартовавшего участника нельзя убрать из протокола', true);
      return;
    }
    page.state.spEntries.splice(index, 1);
    params.renderList();
    params.saveToServer();
  }

  async function manualStartNext(params, existingTarget) {
    const target = existingTarget || params.getTarget();
    if (!target.key) return;

    await params.saveToServer();
    await params.loadProtocol();

    const nextEntry = params.getNextQueueEntry(target);
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
    await params.syncStatus(target, true);
    await page.racePolling.loadRaceStatus();
    page.toast('Старт: #' + nextEntry.rider_number + ' ' + nextEntry.last_name);
  }

  async function launch(params) {
    if (!(await page.ensureJudgeAuth())) return;
    const target = params.getTarget();
    if (!target.key) {
      page.toast('Сначала выберите категории', true);
      return;
    }
    if (target.categoryIds.some(params.isLockedByMassStart)) {
      page.toast('Для выбранных категорий индивидуальный протокол недоступен', true);
      return;
    }
    if (!page.state.spEntries.length) {
      page.toast('Протокол пуст', true);
      return;
    }

    if (params.getRunMode() === 'manual') {
      await manualStartNext(params, target);
      return;
    }

    const state = params.getState(target.key, target.categoryIds);
    const isResume = target.categoryIds.some(function (catId) {
      return params.getCategoryLifecycle(catId).started;
    });
    const resumeDelayMs = isResume && state && state.pausedDelayMs ? state.pausedDelayMs : 0;

    await params.saveToServer();
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
    await params.syncStatus(target, true);
    await page.racePolling.loadRaceStatus();
    page.toast(isResume ? 'Протокол продолжен' : 'Протокол запущен');
  }

  async function stop(params) {
    if (!(await page.ensureJudgeAuth())) return;
    const target = params.getTarget();
    if (!target.key) return;

    const pausedDelayMs = params.computePausedDelayMs(target.key);
    const result = await page.api.stopStartProtocol(target.payload);
    if (!page.isResponseOk(result)) {
      page.toast(page.getResponseError(result, 'Ошибка остановки'), true);
      return;
    }

    params.clearStateFor(target.key);
    const state = params.getState(target.key, target.categoryIds);
    state.pausedDelayMs = pausedDelayMs;
    params.saveAllStates();
    params.updateUI();
    page.toast('Протокол поставлен на паузу');
  }

  function ensureCountdownTick(params) {
    if (page.state.spCountdownTimer) return;
    page.state.spCountdownTimer = window.setInterval(function () {
      if (page.state.startMode !== 'individual') return;
      params.updateUI();
    }, page.constants.COUNTDOWN_TICK_MS);
  }

  function bind(params) {
    bindSearch(params);

    if (page.els.individualStartScope) {
      page.els.individualStartScope.addEventListener('change', function () {
        sessionStorage.setItem('judge_individual_start_scope', this.value);
        params.updateScopeUI();
        params.switchToCategory();
      });
    }

    if (page.els.individualStartCategoryList) {
      page.els.individualStartCategoryList.addEventListener('change', function () {
        params.saveSelectedIds(params.getSelectedIds());
        params.switchToCategory();
      });
    }

    if (page.els.spRunMode) {
      page.els.spRunMode.addEventListener('change', function () {
        sessionStorage.setItem('judge_sp_run_mode', this.value);
        params.updateUI();
      });
    }

    page.els.spList.addEventListener('click', function (event) {
      const removeBtn = event.target.closest('[data-action="remove-sp-entry"]');
      if (!removeBtn) return;
      removeEntry(params, parseInt(removeBtn.dataset.index, 10));
    });
  }

  page.startProtocolRuntime = {
    bindSearch: bindSearch,
    selectFromSearch: selectFromSearch,
    removeEntry: removeEntry,
    manualStartNext: manualStartNext,
    launch: launch,
    stop: stop,
    ensureCountdownTick: ensureCountdownTick,
    bind: bind,
  };
})();
