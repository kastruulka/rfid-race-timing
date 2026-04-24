(function () {
  const page = window.JudgePage || (window.JudgePage = {});

  function createJudgeActionBindings() {
    function bindActionButtons() {
      page.els.btnModeMass.addEventListener('click', function () {
        page.judgeRaceActions.setStartMode('mass');
      });
      page.els.btnModeIndividual.addEventListener('click', function () {
        page.judgeRaceActions.setStartMode('individual');
      });
      page.els.btnMassStart.addEventListener('click', page.massStart.doMassStart);
      page.els.btnFinishRace.addEventListener('click', page.judgeRaceActions.doFinishRace);
      page.els.btnSpAutoFill.addEventListener('click', page.startProtocol.autoFill);
      page.els.btnSpClear.addEventListener('click', page.startProtocol.clear);
      page.els.btnSpLaunch.addEventListener('click', page.startProtocol.launch);
      page.els.btnSpStop.addEventListener('click', page.startProtocol.stop);
      page.els.btnFinishRaceInd.addEventListener('click', page.judgeRaceActions.doFinishRace);
      page.els.btnIndividualStart.addEventListener(
        'click',
        page.judgeRiderActions.doIndividualStart
      );
      page.els.btnResetCat.addEventListener('click', page.judgeRaceActions.doResetCategory);
      page.els.btnNewRace.addEventListener('click', page.judgeRaceActions.doNewRace);
      page.els.btnAddManualLap.addEventListener('click', page.riderPanel.doAddManualLap);
      page.els.btnEditFinishTime.addEventListener('click', page.judgeRiderActions.doEditFinishTime);
      page.els.btnUnfinishRider.addEventListener('click', page.judgeRiderActions.doUnfinishRider);
      page.els.btnDnfVoluntary.addEventListener('click', function () {
        page.judgeRiderActions.doDNF('voluntary');
      });
      page.els.btnDnfMechanical.addEventListener('click', function () {
        page.judgeRiderActions.doDNF('mechanical');
      });
      page.els.btnDnfInjury.addEventListener('click', function () {
        page.judgeRiderActions.doDNF('injury');
      });
      page.els.btnTimePenalty.addEventListener('click', page.judgeRiderActions.doTimePenalty);
      page.els.btnDsq.addEventListener('click', page.judgeRiderActions.doDSQ);
      page.els.btnExtraLap.addEventListener('click', page.judgeRiderActions.doExtraLap);
      page.els.btnWarning.addEventListener('click', page.judgeRiderActions.doWarning);
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
        [page.els.penReason, page.judgeRiderActions.doTimePenalty],
        [page.els.dsqReason, page.judgeRiderActions.doDSQ],
        [page.els.extraReason, page.judgeRiderActions.doExtraLap],
        [page.els.warnReason, page.judgeRiderActions.doWarning],
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

    return {
      bindActionButtons: bindActionButtons,
      bindSubmitShortcuts: bindSubmitShortcuts,
    };
  }

  page.createJudgeActionBindings = createJudgeActionBindings;
})();
