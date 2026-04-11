(function () {
  function finish() {
    document.body.classList.remove('page-hydration-pending');
  }

  function start() {
    document.body.classList.add('page-hydration-pending');
  }

  window.pageHydration = {
    finish: finish,
    start: start,
  };
})();
