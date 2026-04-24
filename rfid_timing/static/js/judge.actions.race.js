(function () {
  const page = window.JudgePage || (window.JudgePage = {});
  const helpers = page.judgeActionHelpers;

  function setStartMode(mode, options) {
    const opts = Object.assign(
      {
        persist: true,
        syncProtocol: true,
      },
      options || {}
    );
    page.state.startMode = mode;
    if (opts.persist) {
      try {
        localStorage.setItem('judge_start_mode', mode);
      } catch {
        // Ignore storage write failures.
      }
      try {
        sessionStorage.setItem('judge_start_mode', mode);
      } catch {
        // Ignore storage write failures.
      }
    }
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
    if (opts.syncProtocol) page.startProtocol.switchToCategory();
  }

  async function doFinishRace() {
    if (!(await helpers.ensureActionAuth())) return;
    const catId = helpers.ensureSelectedCategory(page.messages.selectCategory);
    if (!catId) return;

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
    if (!(await helpers.ensureActionAuth())) return;
    const catId = helpers.ensureSelectedCategory('Выберите категорию для сброса');
    if (!catId) return;

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
    if (!(await helpers.ensureActionAuth())) return;
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

  page.judgeRaceActions = {
    doFinishRace: doFinishRace,
    doNewRace: doNewRace,
    doResetCategory: doResetCategory,
    setStartMode: setStartMode,
  };
})();
