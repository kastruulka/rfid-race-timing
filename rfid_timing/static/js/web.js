function fmtMs(ms) {
  if (ms === null || ms === undefined) return '—';
  const totalSec = Math.abs(ms) / 1000;
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return String(m).padStart(2, '0') + ':' + s.toFixed(1).padStart(4, '0');
}

let serverElapsedMs = null;   // elapsed на момент последнего ответа сервера
let perfAtSync = null;        // performance.now() в момент синхронизации
let clockTimer = null;
let lastFeedIds = '';         // для предотвращения мигания

function updateClock() {
  if (serverElapsedMs === null) return;
  const localDelta = performance.now() - perfAtSync;
  const elapsed = serverElapsedMs + localDelta;
  document.getElementById('main-clock').textContent = fmtMs(elapsed);
}

function getSelectedCategory() {
  const sel = document.getElementById('category-select');
  return sel ? sel.value : '';
}

async function fetchState() {
  try {
    const catId = getSelectedCategory();
    const qs = catId ? '?category_id=' + encodeURIComponent(catId) : '';
    const resp = await fetch('/api/state' + qs);
    const data = await resp.json();

    if (data.race_closed) {
      if (clockTimer) { clearInterval(clockTimer); clockTimer = null; }
      if (data.server_elapsed_ms !== null) {
        document.getElementById('main-clock').textContent = fmtMs(data.server_elapsed_ms);
        document.getElementById('main-clock').style.color = 'var(--text-dim)';
      }
    } else if (data.server_elapsed_ms !== null && data.server_elapsed_ms !== undefined) {
      serverElapsedMs = data.server_elapsed_ms;
      perfAtSync = performance.now();
      document.getElementById('main-clock').style.color = '';
      if (!clockTimer) clockTimer = setInterval(updateClock, 100);
    }

    updateFeed(data.feed);
    updateResults(data.results);
    updateCounters(data.status);
    updateCategories(data.categories);
  } catch (e) {
    console.error('Fetch error', e);
  }
}

function updateFeed(feed) {
  const hash = feed.map(f => f.lap_id).join('|');
  if (hash === lastFeedIds) return;
  lastFeedIds = hash;

  const list = document.getElementById('feed-list');
  const hadChildren = list.children.length > 0;

  list.innerHTML = feed.map((item, i) => {
    const isFinishLap = item.is_finish_lap;
    const isWarmup = item.lap_number === 0;
    let cls = 'feed-item';
    if (isFinishLap) cls += ' finish-item';
    if (isWarmup) cls += ' warmup';
    if (hadChildren && i === 0) cls += ' new-item';

    const lapLabel = isWarmup ? 'разгонный' :
      (isFinishLap ? 'ФИНИШ · круг ' + item.lap_number + '/' + item.laps_required
                   : 'круг ' + item.lap_number + '/' + item.laps_required);

    return '<div class="' + cls + '">' +
      '<div class="feed-number">' + item.rider_number + '</div>' +
      '<div class="feed-info">' +
        '<div class="feed-name">' + item.rider_name + '</div>' +
        '<div class="feed-detail">' + lapLabel + ' · ' + item.time_str + '</div>' +
      '</div>' +
      '<div class="feed-time">' + fmtMs(item.lap_time) + '</div>' +
    '</div>';
  }).join('');
}

function updateResults(results) {
  const tbody = document.getElementById('results-body');
  let leaderTime = null;

  tbody.innerHTML = results.map((r, i) => {
    const pos = r.status === 'FINISHED' ? String(i + 1) : '—';
    if (r.status === 'FINISHED' && leaderTime === null) leaderTime = r.total_time;

    const gap = (r.status === 'FINISHED' && leaderTime !== null && r.total_time !== leaderTime)
      ? '+' + fmtMs(r.total_time - leaderTime) : '';

    let penaltyTag = '';
    if (r.penalty_time_ms > 0) {
      penaltyTag = '<span style="color:var(--orange);font-size:11px;margin-left:4px">(+' +
        (r.penalty_time_ms / 1000).toFixed(0) + 'с)</span>';
    }

    let lapsStr = r.laps_done + '/' + r.laps_required;
    if (r.extra_laps > 0) {
      lapsStr += '<span style="color:var(--orange);font-size:10px;margin-left:2px">+' + r.extra_laps + '</span>';
    }

    let statusHtml;
    if (r.laps_complete) {
      statusHtml = '<span class="status-tag" style="background:var(--green-glow);color:var(--green)">ОЖИДАНИЕ</span>';
    } else {
      statusHtml = '<span class="status-tag status-' + r.status + '">' + r.status + '</span>';
    }
    if (r.status === 'DNF' && r.dnf_reason) {
      statusHtml += '<div style="font-size:9px;color:var(--text-dim);margin-top:2px">' + r.dnf_reason + '</div>';
    }

    return '<tr>' +
      '<td class="col-pos">' + pos + '</td>' +
      '<td class="col-num">' + r.number + '</td>' +
      '<td class="col-name">' + r.name + '</td>' +
      '<td class="col-club">' + (r.club || '') + '</td>' +
      '<td class="col-laps">' + lapsStr + '</td>' +
      '<td class="col-lastlap">' + fmtMs(r.last_lap_time) + '</td>' +
      '<td class="col-time">' + fmtMs(r.total_time) + penaltyTag + '</td>' +
      '<td class="col-gap">' + gap + '</td>' +
      '<td class="col-status">' + statusHtml + '</td>' +
    '</tr>';
  }).join('');
}

function updateCounters(st) {
  document.getElementById('cnt-racing').textContent = st.RACING || 0;
  document.getElementById('cnt-finished').textContent = st.FINISHED || 0;
  document.getElementById('cnt-dnf').textContent = (st.DNF || 0) + (st.DSQ || 0);
}

let catsLoaded = false;
function updateCategories(cats) {
  if (catsLoaded || !cats || !cats.length) return;
  const sel = document.getElementById('category-select');
  cats.forEach(c => {
    const o = document.createElement('option');
    o.value = c.id;
    o.textContent = c.name + ' (' + c.laps + ' кр.)';
    sel.appendChild(o);
  });
  catsLoaded = true;
}

document.getElementById('category-select').addEventListener('change', () => {
  fetchState();
});
fetchState();
setInterval(fetchState, 1000);