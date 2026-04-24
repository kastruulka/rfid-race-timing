(function () {
  const page = window.JudgePage || (window.JudgePage = {});

  function getStoredSelectedIds() {
    const raw = sessionStorage.getItem('judge_mass_start_selected') || '';
    return raw
      .split(',')
      .map(function (value) {
        return value.trim();
      })
      .filter(Boolean);
  }

  function saveSelectedIds(ids) {
    sessionStorage.setItem('judge_mass_start_selected', (ids || []).join(','));
  }

  function getScope() {
    return page.els.massStartScope ? page.els.massStartScope.value : 'current';
  }

  function getSelectedIds() {
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

  function getTargetCategoryIds() {
    const scope = getScope();
    if (scope === 'all') return getAllCategoryIds();
    if (scope === 'selected') return getSelectedIds();
    const currentId = page.getCatId();
    return currentId ? [String(currentId)] : [];
  }

  function getTargetSummary(targetIds) {
    const all = (targetIds || []).filter(Boolean);
    const active = all.filter(function (catId) {
      const lifecycle = page.getCategoryLifecycle(catId);
      return !lifecycle.started && !lifecycle.closed;
    });
    return { all: all, active: active };
  }

  function getButtonLabel(summary) {
    if (!summary.all.length) return 'Выберите категории';
    if (!summary.active.length) return 'Старт недоступен';
    if (summary.active.length === 1) return '▶ Масс-старт';
    return '▶ Масс-старт x' + summary.active.length;
  }

  function updateScopeUI() {
    if (!page.els.massStartSelectedWrap) return;
    page.els.massStartSelectedWrap.style.display = getScope() === 'selected' ? 'block' : 'none';
  }

  function renderCategoryOptions() {
    if (!page.els.massStartCategoryList) return;
    const selectedIds = new Set(getStoredSelectedIds());
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

  function updateControls() {
    updateScopeUI();
    const summary = getTargetSummary(getTargetCategoryIds());
    page.setStateDisabled(page.els.btnMassStart, !summary.active.length);
    page.els.btnMassStart.textContent = getButtonLabel(summary);
  }

  async function doMassStart() {
    if (!(await page.ensureJudgeAuth())) return;
    if (page.els.btnMassStart.disabled) {
      page.toast(page.els.btnMassStart.textContent || 'Старт уже недоступен', true);
      return;
    }

    const summary = getTargetSummary(getTargetCategoryIds());
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
        updateControls();
        page.toast('Масс-старт! Участников: ' + (((data || {}).info || {}).riders_started || '?'));
        await page.racePolling.loadRaceStatus();
        return;
      }
      page.toast(page.getResponseError(result, 'Ошибка старта'), true);
      return;
    }

    if (getScope() !== 'current') {
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

  page.renderMassStartCategoryOptions = renderCategoryOptions;
  page.updateMassStartControls = updateControls;
  page.massStart = {
    getStoredSelectedIds: getStoredSelectedIds,
    saveSelectedIds: saveSelectedIds,
    getScope: getScope,
    getSelectedIds: getSelectedIds,
    getAllCategoryIds: getAllCategoryIds,
    getTargetCategoryIds: getTargetCategoryIds,
    getTargetSummary: getTargetSummary,
    updateScopeUI: updateScopeUI,
    renderCategoryOptions: renderCategoryOptions,
    updateControls: updateControls,
    doMassStart: doMassStart,
  };
})();
