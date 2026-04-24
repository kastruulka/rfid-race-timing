(function () {
  const page = window.JudgePage || (window.JudgePage = {});

  function getSelectedRiderLabel() {
    const rider = page.state.riders.find(function (entry) {
      return entry.id === page.state.selectedRiderId;
    });
    return rider ? '#' + rider.number + ' ' + rider.last_name : '#' + page.state.selectedRiderId;
  }

  async function ensureActionAuth() {
    return page.ensureJudgeAuth();
  }

  function ensureSelectedRider() {
    return page.requireRider();
  }

  function ensureSelectedCategory(message) {
    const catId = page.getCatId();
    if (catId) return catId;
    page.toast(message || page.messages.selectCategory, true);
    return null;
  }

  async function runApiAction(options) {
    if (!(await ensureActionAuth())) return false;
    if (options.requireRider && !ensureSelectedRider()) return false;
    if (options.requireCategory && !ensureSelectedCategory(options.categoryMessage)) return false;
    if (options.before && (await options.before()) === false) return false;

    const result = await options.run();
    const ok = page.isResponseOk ? page.isResponseOk(result) : !!result.ok;
    if (!ok) {
      page.toast(
        page.getResponseError
          ? page.getResponseError(result, options.errorMessage || 'Ошибка')
          : result.error || options.errorMessage || 'Ошибка',
        true
      );
      return false;
    }

    if (options.onSuccess) {
      await options.onSuccess(result);
    }
    return true;
  }

  page.judgeActionHelpers = {
    ensureActionAuth: ensureActionAuth,
    ensureSelectedCategory: ensureSelectedCategory,
    ensureSelectedRider: ensureSelectedRider,
    getSelectedRiderLabel: getSelectedRiderLabel,
    runApiAction: runApiAction,
  };
})();
