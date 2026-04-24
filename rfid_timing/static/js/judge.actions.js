(function () {
  const page = window.JudgePage || (window.JudgePage = {});
  const bindings = page.createJudgeActionBindings();

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
    bindActionButtons: bindings.bindActionButtons,
    bindSubmitShortcuts: bindings.bindSubmitShortcuts,
    init: initJudgeActionsLayer,
  };
})();
