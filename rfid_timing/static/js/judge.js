(function () {
  const page = window.JudgePage || (window.JudgePage = {});

  function initModule(name) {
    const module = page[name];
    if (module && typeof module.init === 'function') module.init();
  }

  ['dom', 'sync', 'judgeActions'].forEach(initModule);

  page.destroy = function destroyJudgePage() {
    if (page.bootstrap && typeof page.bootstrap.destroy === 'function') {
      page.bootstrap.destroy();
    }
  };

  if (!page.bootstrap || typeof page.bootstrap.init !== 'function') {
    throw new Error('Judge bootstrap module is not loaded');
  }

  page.bootstrap.init();
})();
