(function () {
  const page = window.JudgePage || (window.JudgePage = {});

  function clearSelectedRider() {
    page.state.selectedRiderId = null;
    page.state.lastLapsHash = '';
    page.els.riderSearch.value = '';
    page.els.selectedInfo.classList.remove('visible');
    page.els.srNum.textContent = '';
    page.els.srName.textContent = '';
    page.els.srMeta.textContent = '';
    page.els.srStatus.innerHTML = '';
    page.els.currentFinishInfo.style.display = 'none';
    page.els.noFinishInfo.style.display = 'none';
    page.els.currentFinishTime.textContent = '';
    page.els.editFinishMm.value = '';
    page.els.editFinishSs.value = '';
    page.els.lapsList.innerHTML =
      '<div style="font-size:11px;color:var(--text-dim);padding:4px 0">Выберите участника</div>';
    if (page.state.riderDropdown) page.state.riderDropdown.close();
  }

  function bindSearch() {
    const savedFilter = sessionStorage.getItem('judge_filter_current_category');
    if (savedFilter !== null) {
      page.els.searchFilterCat.checked = savedFilter === 'true';
    }

    page.state.riderDropdown = page.createRiderDropdown({
      inputEl: page.els.riderSearch,
      listEl: page.els.riderDropdown,
      source: function () {
        const query = String(page.els.riderSearch.value || '').toLowerCase();
        const filterByCat = page.els.searchFilterCat.checked;
        const catId = page.getCatId();
        return page.state.riders.filter(function (rider) {
          if (filterByCat && catId && String(rider.category_id) !== String(catId)) return false;
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
      emptyText: 'Не найдено',
      renderMeta: function (rider) {
        if (page.els.searchFilterCat.checked || !rider.category_name) return null;
        const meta = document.createElement('span');
        meta.style.fontSize = '9px';
        meta.style.color = 'var(--text-dim)';
        meta.style.marginLeft = 'auto';
        meta.textContent = rider.category_name;
        return meta;
      },
      onSelect: function (rider) {
        selectRider(rider.id);
      },
      onClear: function () {
        clearSelectedRider();
      },
    });
  }

  function selectRider(riderId) {
    page.state.selectedRiderId = riderId;
    const rider = page.state.riders.find(function (entry) {
      return entry.id === riderId;
    });
    if (page.state.riderDropdown) page.state.riderDropdown.close();
    if (!rider) return;
    page.els.riderSearch.value =
      '#' + rider.number + ' ' + rider.last_name + ' ' + (rider.first_name || '');
    page.els.srNum.textContent = '#' + rider.number;
    page.els.srName.textContent = rider.last_name + ' ' + (rider.first_name || '');
    page.els.srMeta.textContent =
      (rider.category_name || '—') + ' · ' + (rider.club || '—') + ' · ' + (rider.city || '');
    page.els.selectedInfo.classList.add('visible');
    page.state.lastLapsHash = '';
    loadRiderFinishInfo(riderId);
    loadRiderLaps(riderId);
  }

  async function loadRiderFinishInfo(riderId) {
    try {
      const data = page.getResponseData(await page.api.getRiderStatus(riderId));
      if (data.status === 'FINISHED' && data.total_time_ms != null) {
        const ms = data.total_time_ms;
        const minutes = Math.floor(Math.abs(ms) / 1000 / 60);
        const seconds = (Math.abs(ms) / 1000) % 60;
        page.els.currentFinishTime.textContent =
          String(minutes).padStart(2, '0') + ':' + seconds.toFixed(1).padStart(4, '0');
        page.els.editFinishMm.value = String(minutes);
        page.els.editFinishSs.value = seconds.toFixed(1);
        page.els.currentFinishInfo.style.display = 'block';
        page.els.noFinishInfo.style.display = 'none';
        page.els.srStatus.innerHTML =
          '<span style="color:var(--green);font-weight:700;font-size:12px">FINISHED</span>';
      } else {
        page.els.currentFinishInfo.style.display = 'none';
        page.els.noFinishInfo.style.display = data.status === 'RACING' ? 'block' : 'none';
        page.els.editFinishMm.value = '';
        page.els.editFinishSs.value = '';
        const color =
          data.status === 'RACING'
            ? 'var(--accent)'
            : data.status === 'DNF' || data.status === 'DSQ'
              ? 'var(--red)'
              : 'var(--text-dim)';
        page.els.srStatus.innerHTML =
          '<span style="font-weight:700;font-size:12px;color:' +
          color +
          '">' +
          (data.status || '—') +
          '</span>' +
          (data.dnf_reason
            ? '<span style="font-size:10px;color:var(--text-dim);margin-left:6px">' +
              data.dnf_reason +
              '</span>'
            : '');
      }
    } catch {
      page.els.currentFinishInfo.style.display = 'none';
      page.els.noFinishInfo.style.display = 'none';
    }
  }

  function buildLapRow(lap) {
    const row = document.createElement('div');
    row.className = 'lap-row';
    row.id = 'lap-row-' + lap.id;
    row.innerHTML =
      '<span class="lr-num">' +
      (lap.lap_number === 0 ? '0' : lap.lap_number) +
      '</span>' +
      '<span class="lr-time">' +
      page.fmtMs(lap.lap_time) +
      '</span>' +
      '<input id="lap-mm-' +
      lap.id +
      '" placeholder="М" value="' +
      Math.floor(Math.abs(lap.lap_time || 0) / 1000 / 60) +
      '">' +
      '<span style="color:var(--text-dim)">:</span>' +
      '<input id="lap-ss-' +
      lap.id +
      '" placeholder="С.д" style="width:50px" value="' +
      ((Math.abs(lap.lap_time || 0) / 1000) % 60).toFixed(1) +
      '">' +
      '<span class="lr-btn save" data-action="save-lap" data-lap-id="' +
      lap.id +
      '">✓</span>' +
      '<span class="lr-btn del" data-action="delete-lap" data-lap-id="' +
      lap.id +
      '">✕</span>';
    return row;
  }

  async function loadRiderLaps(riderId) {
    try {
      const data = page.getResponseData(await page.api.getRiderLaps(riderId));
      const laps = Array.isArray(data) ? data : [];
      if (!laps.length) {
        page.state.lastLapsHash = '';
        page.els.lapsList.innerHTML =
          '<div style="font-size:11px;color:var(--text-dim);padding:4px 0">Нет зафиксированных кругов</div>';
        return;
      }
      const newHash = laps
        .map(function (lap) {
          return lap.id + ':' + lap.lap_number + ':' + lap.lap_time;
        })
        .join('|');
      if (newHash === page.state.lastLapsHash) return;
      const focused = document.activeElement;
      if (focused && focused.id && focused.id.startsWith('lap-')) {
        const existingIds = new Set();
        page.els.lapsList.querySelectorAll('.lap-row').forEach(function (row) {
          existingIds.add(parseInt(row.id.replace('lap-row-', ''), 10));
        });
        laps.forEach(function (lap) {
          if (!existingIds.has(lap.id)) page.els.lapsList.appendChild(buildLapRow(lap));
        });
        page.state.lastLapsHash = newHash;
        return;
      }
      page.state.lastLapsHash = newHash;
      page.els.lapsList.innerHTML = '';
      laps.forEach(function (lap) {
        page.els.lapsList.appendChild(buildLapRow(lap));
      });
    } catch {
      page.state.lastLapsHash = '';
      page.els.lapsList.innerHTML =
        '<div style="font-size:11px;color:var(--text-dim);padding:4px 0">Не удалось загрузить круги</div>';
    }
  }

  async function refreshRiderPanel() {
    if (!page.state.selectedRiderId || page.state.riderPanelRequestInFlight) return;
    page.state.riderPanelRequestInFlight = true;
    try {
      await loadRiderFinishInfo(page.state.selectedRiderId);
      await loadRiderLaps(page.state.selectedRiderId);
    } finally {
      page.state.riderPanelRequestInFlight = false;
    }
  }

  async function saveLap(lapId) {
    if (!(await page.ensureJudgeAuth())) return;
    const minutes = parseInt(document.getElementById('lap-mm-' + lapId).value.trim(), 10) || 0;
    const seconds = parseFloat(document.getElementById('lap-ss-' + lapId).value.trim()) || 0;
    if (seconds >= 60 || seconds < 0) {
      page.toast('Неверное время', true);
      page.state.lastLapsHash = '';
      await refreshRiderPanel();
      return;
    }
    const result = await page.api.updateLap(lapId, Math.round((minutes * 60 + seconds) * 1000));
    if (result.ok) {
      page.toast('Круг обновлён');
      page.state.lastLapsHash = '';
      await refreshRiderPanel();
    } else {
      page.toast(result.error || 'Ошибка', true);
      page.state.lastLapsHash = '';
      await refreshRiderPanel();
    }
  }

  async function deleteLap(lapId) {
    if (!(await page.ensureJudgeAuth())) return;
    if (!window.confirm('Удалить этот круг?')) return;
    const result = await page.api.deleteLap(lapId);
    if (result.ok) {
      page.toast('Круг удалён');
      page.state.lastLapsHash = '';
      await refreshRiderPanel();
      page.racePolling.loadRaceStatus();
    } else {
      page.toast(result.error || 'Ошибка', true);
    }
  }

  async function doAddManualLap() {
    if (!(await page.ensureJudgeAuth())) return;
    if (!page.requireRider()) return;
    const result = await page.api.addManualLap(page.state.selectedRiderId);
    if (result.ok) {
      page.toast('Круг добавлен');
      page.state.lastLapsHash = '';
      await refreshRiderPanel();
      page.racePolling.loadRaceStatus();
    } else {
      page.toast(result.error || 'Ошибка', true);
    }
  }

  function bind() {
    bindSearch();
    page.els.searchFilterCat.addEventListener('change', function () {
      sessionStorage.setItem('judge_filter_current_category', this.checked ? 'true' : 'false');
      if (page.state.riderDropdown) page.state.riderDropdown.render();
    });
    page.els.lapsList.addEventListener('click', function (event) {
      const action = event.target.closest('[data-action]');
      if (!action) return;
      const lapId = parseInt(action.dataset.lapId, 10);
      if (action.dataset.action === 'save-lap') saveLap(lapId);
      if (action.dataset.action === 'delete-lap') deleteLap(lapId);
    });
  }

  page.riderPanel = {
    bind: bind,
    clearSelectedRider: clearSelectedRider,
    selectRider: selectRider,
    loadRiderFinishInfo: loadRiderFinishInfo,
    loadRiderLaps: loadRiderLaps,
    refreshRiderPanel: refreshRiderPanel,
    saveLap: saveLap,
    deleteLap: deleteLap,
    doAddManualLap: doAddManualLap,
  };
})();
