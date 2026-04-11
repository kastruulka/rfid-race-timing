const WEB_CONFIG = {
  STATE_POLL_MS: 500,
  CLOCK_TICK_MS: 100,
};

const els = {
  clock: document.getElementById('main-clock'),
  categorySelect: document.getElementById('category-select'),
  feedList: document.getElementById('feed-list'),
  resultsBody: document.getElementById('results-body'),
  racingCount: document.getElementById('cnt-racing'),
  finishedCount: document.getElementById('cnt-finished'),
  dnfCount: document.getElementById('cnt-dnf'),
};

const state = {
  clock: {
    serverElapsedMs: null,
    perfAtSync: null,
    timerId: null,
  },
  polling: {
    timerId: null,
    fetchInFlight: false,
  },
  selectedCategory: '',
  lastFeedIds: '',
  categoryOptionsHash: '',
};

function fmtMs(ms) {
  if (ms === null || ms === undefined) return '-';
  const totalSec = Math.abs(ms) / 1000;
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return String(m).padStart(2, '0') + ':' + s.toFixed(1).padStart(4, '0');
}

function clearElement(el) {
  while (el.firstChild) {
    el.removeChild(el.firstChild);
  }
}

function appendText(el, text) {
  el.textContent = text === null || text === undefined ? '' : String(text);
}

function stopClock() {
  if (!state.clock.timerId) return;
  clearInterval(state.clock.timerId);
  state.clock.timerId = null;
}

function setClockDisplay(text, color) {
  appendText(els.clock, text);
  els.clock.style.color = color || '';
}

function updateClock() {
  if (state.clock.serverElapsedMs === null || state.clock.perfAtSync === null) return;
  const localDelta = performance.now() - state.clock.perfAtSync;
  setClockDisplay(fmtMs(state.clock.serverElapsedMs + localDelta), '');
}

function ensureClockTicking() {
  if (state.clock.timerId) return;
  state.clock.timerId = setInterval(updateClock, WEB_CONFIG.CLOCK_TICK_MS);
}

function syncClockFromCategoryState(snapshot) {
  if (!snapshot) {
    state.clock.serverElapsedMs = null;
    state.clock.perfAtSync = null;
    stopClock();
    setClockDisplay('00:00.0', '');
    return;
  }

  if (snapshot.closed) {
    state.clock.serverElapsedMs = null;
    state.clock.perfAtSync = null;
    stopClock();
    setClockDisplay(
      snapshot.elapsed_ms !== null && snapshot.elapsed_ms !== undefined
        ? fmtMs(snapshot.elapsed_ms)
        : '00:00.0',
      'var(--text-dim)'
    );
    return;
  }

  if (snapshot.elapsed_ms !== null && snapshot.elapsed_ms !== undefined) {
    state.clock.serverElapsedMs = snapshot.elapsed_ms;
    state.clock.perfAtSync = performance.now();
    ensureClockTicking();
    updateClock();
    return;
  }

  state.clock.serverElapsedMs = null;
  state.clock.perfAtSync = null;
  stopClock();
  setClockDisplay('00:00.0', '');
}

function getSelectedCategory() {
  return els.categorySelect ? els.categorySelect.value : '';
}

function getMaxActiveCategoryElapsed(catStates) {
  let maxElapsed = null;

  Object.values(catStates || {}).forEach(function (categoryState) {
    if (
      !categoryState ||
      categoryState.closed ||
      categoryState.elapsed_ms === null ||
      categoryState.elapsed_ms === undefined
    ) {
      return;
    }
    if (maxElapsed === null || categoryState.elapsed_ms > maxElapsed) {
      maxElapsed = categoryState.elapsed_ms;
    }
  });

  return maxElapsed;
}

function getLastClosedCategorySnapshot(catStates) {
  let latest = null;

  Object.values(catStates || {}).forEach(function (categoryState) {
    if (
      !categoryState ||
      !categoryState.closed ||
      categoryState.elapsed_ms === null ||
      categoryState.elapsed_ms === undefined
    ) {
      return;
    }
    if (latest === null || (categoryState.closed_at || 0) > (latest.closed_at || 0)) {
      latest = categoryState;
    }
  });

  return latest;
}

function deriveViewModel(data, selectedCategory) {
  const catStates = data.category_states || {};
  const selectedSnapshot = selectedCategory ? catStates[String(selectedCategory)] || null : null;
  const maxActiveElapsed = getMaxActiveCategoryElapsed(catStates);
  const lastClosedSnapshot = getLastClosedCategorySnapshot(catStates);

  let clockSnapshot = null;
  if (selectedCategory) {
    clockSnapshot = selectedSnapshot || { elapsed_ms: null, closed: false };
  } else if (maxActiveElapsed !== null) {
    clockSnapshot = { elapsed_ms: maxActiveElapsed, closed: false };
  } else if (lastClosedSnapshot) {
    clockSnapshot = lastClosedSnapshot;
  }

  return {
    clockSnapshot: clockSnapshot,
    feed: Array.isArray(data.feed) ? data.feed : [],
    results: Array.isArray(data.results) ? data.results : [],
    counters: data.status || {},
    categories: Array.isArray(data.categories) ? data.categories : [],
  };
}

function buildFeedItem(item, isNewItem) {
  const wrapper = document.createElement('div');
  wrapper.className = 'feed-item';

  if (item.is_finish_lap) wrapper.classList.add('finish-item');
  if (item.lap_number === 0) wrapper.classList.add('warmup');
  if (isNewItem) wrapper.classList.add('new-item');

  const number = document.createElement('div');
  number.className = 'feed-number';
  appendText(number, item.rider_number);

  const info = document.createElement('div');
  info.className = 'feed-info';

  const name = document.createElement('div');
  name.className = 'feed-name';
  appendText(name, item.rider_name);

  const detail = document.createElement('div');
  detail.className = 'feed-detail';
  const lapLabel =
    item.lap_number === 0
      ? 'разгонный'
      : item.is_finish_lap
        ? 'ФИНИШ - круг ' + item.lap_number + '/' + item.laps_required
        : 'круг ' + item.lap_number + '/' + item.laps_required;
  appendText(detail, lapLabel + ' - ' + item.time_str);

  const time = document.createElement('div');
  time.className = 'feed-time';
  appendText(time, fmtMs(item.lap_time));

  info.appendChild(name);
  info.appendChild(detail);
  wrapper.appendChild(number);
  wrapper.appendChild(info);
  wrapper.appendChild(time);

  return wrapper;
}

function updateFeed(feed) {
  const hash = feed
    .map(function (item) {
      return item.lap_id;
    })
    .join('|');
  if (hash === state.lastFeedIds) return;

  const hadChildren = els.feedList.children.length > 0;
  clearElement(els.feedList);

  feed.forEach(function (item, index) {
    els.feedList.appendChild(buildFeedItem(item, hadChildren && index === 0));
  });

  state.lastFeedIds = hash;
}

function createPenaltyTag(penaltyTimeMs) {
  if (!(penaltyTimeMs > 0)) return null;

  const tag = document.createElement('span');
  tag.style.color = 'var(--orange)';
  tag.style.fontSize = '11px';
  tag.style.marginLeft = '4px';
  appendText(tag, '(+' + (penaltyTimeMs / 1000).toFixed(0) + 'с)');
  return tag;
}

function createLapsCell(result) {
  const cell = document.createElement('td');
  cell.className = 'col-laps';
  appendText(cell, result.laps_done + '/' + result.laps_required);

  if (result.extra_laps > 0) {
    const tag = document.createElement('span');
    tag.style.color = 'var(--orange)';
    tag.style.fontSize = '10px';
    tag.style.marginLeft = '2px';
    appendText(tag, '+' + result.extra_laps);
    cell.appendChild(tag);
  }

  return cell;
}

function createStatusCell(result) {
  const cell = document.createElement('td');
  cell.className = 'col-status';

  const statusTag = document.createElement('span');
  statusTag.className = result.laps_complete ? 'status-tag' : 'status-tag status-' + result.status;

  if (result.laps_complete) {
    statusTag.style.background = 'var(--green-glow)';
    statusTag.style.color = 'var(--green)';
    appendText(statusTag, 'ОЖИДАНИЕ');
  } else {
    appendText(statusTag, result.status);
  }

  cell.appendChild(statusTag);

  if (result.status === 'DNF' && result.dnf_reason) {
    const reason = document.createElement('div');
    reason.style.fontSize = '9px';
    reason.style.color = 'var(--text-dim)';
    reason.style.marginTop = '2px';
    appendText(reason, result.dnf_reason);
    cell.appendChild(reason);
  }

  return cell;
}

function createTextCell(className, text) {
  const cell = document.createElement('td');
  cell.className = className;
  appendText(cell, text);
  return cell;
}

function updateResults(results) {
  clearElement(els.resultsBody);

  let leaderTime = null;
  results.forEach(function (result, index) {
    const row = document.createElement('tr');
    const position = result.status === 'FINISHED' ? String(index + 1) : '-';

    if (result.status === 'FINISHED' && leaderTime === null) {
      leaderTime = result.total_time;
    }

    const gap =
      result.status === 'FINISHED' && leaderTime !== null && result.total_time !== leaderTime
        ? '+' + fmtMs(result.total_time - leaderTime)
        : '';

    const timeCell = createTextCell('col-time', fmtMs(result.total_time));
    const penaltyTag = createPenaltyTag(result.penalty_time_ms);
    if (penaltyTag) timeCell.appendChild(penaltyTag);

    row.appendChild(createTextCell('col-pos', position));
    row.appendChild(createTextCell('col-num', result.number));
    row.appendChild(createTextCell('col-name', result.name));
    row.appendChild(createTextCell('col-club', result.club || ''));
    row.appendChild(createLapsCell(result));
    row.appendChild(createTextCell('col-lastlap', fmtMs(result.last_lap_time)));
    row.appendChild(timeCell);
    row.appendChild(createTextCell('col-gap', gap));
    row.appendChild(createStatusCell(result));

    els.resultsBody.appendChild(row);
  });
}

function updateCounters(counters) {
  appendText(els.racingCount, counters.RACING || 0);
  appendText(els.finishedCount, counters.FINISHED || 0);
  appendText(els.dnfCount, (counters.DNF || 0) + (counters.DSQ || 0));
}

function updateCategories(categories) {
  const nextHash = categories
    .map(function (category) {
      return [category.id, category.name, category.laps].join(':');
    })
    .join('|');

  if (nextHash === state.categoryOptionsHash) return;

  const selectedValue = getSelectedCategory();
  clearElement(els.categorySelect);

  const allOption = document.createElement('option');
  allOption.value = '';
  allOption.textContent = 'Все категории';
  els.categorySelect.appendChild(allOption);

  categories.forEach(function (category) {
    const option = document.createElement('option');
    option.value = category.id;
    option.textContent = category.name + ' (' + category.laps + ' кр.)';
    els.categorySelect.appendChild(option);
  });

  const hasSelectedCategory = categories.some(function (category) {
    return String(category.id) === String(selectedValue);
  });
  els.categorySelect.value = hasSelectedCategory ? selectedValue : '';
  state.selectedCategory = els.categorySelect.value;
  state.categoryOptionsHash = nextHash;
}

async function fetchState() {
  if (state.polling.fetchInFlight) return;
  state.polling.fetchInFlight = true;

  try {
    const selectedCategory = getSelectedCategory();
    const query = selectedCategory ? '?category_id=' + encodeURIComponent(selectedCategory) : '';
    const response = await window.httpClient.fetchJson('/api/state' + query);
    if (!response.ok || !response.data) {
      throw new Error('State request failed with status ' + response.status);
    }
    const data = response.data;
    const viewModel = deriveViewModel(data, selectedCategory);

    state.selectedCategory = selectedCategory;
    syncClockFromCategoryState(viewModel.clockSnapshot);
    updateFeed(viewModel.feed);
    updateResults(viewModel.results);
    updateCounters(viewModel.counters);
    updateCategories(viewModel.categories);
  } catch (error) {
    console.error('Fetch error', error);
  } finally {
    state.polling.fetchInFlight = false;
  }
}

function startPolling() {
  if (state.polling.timerId) return;
  fetchState();
  state.polling.timerId = setInterval(fetchState, WEB_CONFIG.STATE_POLL_MS);
}

function stopPolling() {
  if (!state.polling.timerId) return;
  clearInterval(state.polling.timerId);
  state.polling.timerId = null;
}

function handleCategoryChange() {
  state.selectedCategory = getSelectedCategory();
  syncClockFromCategoryState(null);
  fetchState();
}

function initWebScoreboard() {
  state.selectedCategory = getSelectedCategory();
  els.categorySelect.addEventListener('change', handleCategoryChange);

  document.addEventListener('visibilitychange', function () {
    if (document.hidden) {
      stopPolling();
      stopClock();
      return;
    }

    if (state.clock.serverElapsedMs !== null) {
      state.clock.perfAtSync = performance.now();
      ensureClockTicking();
      updateClock();
    }
    startPolling();
  });

  window.addEventListener('beforeunload', function () {
    stopPolling();
    stopClock();
  });

  startPolling();
}

initWebScoreboard();
