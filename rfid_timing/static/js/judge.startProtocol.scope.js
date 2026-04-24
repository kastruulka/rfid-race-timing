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

  function hasProtocolPlan(catId) {
    if (
      typeof page.startProtocolHasProtocolPlan === 'function' &&
      page.startProtocolHasProtocolPlan !== hasProtocolPlan
    ) {
      return !!page.startProtocolHasProtocolPlan(catId);
    }
    return false;
  }

  function isLockedByMassStart(catId) {
    const lifecycle = getCategoryLifecycle(catId);
    return !!(catId && lifecycle.started && !lifecycle.closed && !hasProtocolPlan(catId));
  }

  function getTargetCategoryIds() {
    const scope = getScope();
    if (scope === 'all') {
      return getAllCategoryIds().filter(function (catId) {
        return !isLockedByMassStart(catId);
      });
    }
    if (scope === 'selected') {
      return getSelectedIds().filter(function (catId) {
        return !isLockedByMassStart(catId);
      });
    }
    const catId = page.getCatId();
    return catId ? [String(catId)] : [];
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

  page.startProtocolScope = {
    getCategoryLifecycle: getCategoryLifecycle,
    getScope: getScope,
    getStoredSelectedIds: getStoredSelectedIds,
    saveSelectedIds: saveSelectedIds,
    getSelectedIds: getSelectedIds,
    getAllCategoryIds: getAllCategoryIds,
    getTargetCategoryIds: getTargetCategoryIds,
    getTargetKey: getTargetKey,
    getTargetPayload: getTargetPayload,
    getTarget: getTarget,
    isLockedByMassStart: isLockedByMassStart,
  };
})();
