let allRiders = [];
let categories = [];
let selectedCatId = '';

function toast(msg, isError) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast show' + (isError ? ' error' : '');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.className = 'toast', 2500);
}

async function api(url, method, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const r = await fetch(url, opts);
  return r.json();
}

async function loadAll() {
  categories = await api('/api/categories', 'GET');
  renderCategories();
  await loadRiders();
}

async function loadRiders() {
  const qs = selectedCatId ? '?category_id=' + selectedCatId : '';
  allRiders = await api('/api/riders' + qs, 'GET');
  renderRiders();
  updateStats();
}

function renderCategories() {
  const list = document.getElementById('cat-list');
  const allItem = list.querySelector('[data-id=""]');
  list.innerHTML = '';
  list.appendChild(allItem);

  let totalRiders = 0;
  categories.forEach(c => {
    const div = document.createElement('div');
    div.className = 'cat-item' + (selectedCatId == c.id ? ' active' : '');
    div.dataset.id = c.id;
    div.onclick = () => selectCategory(div, c.id);
    div.innerHTML =
      '<div>' +
        '<div class="cat-name">' + esc(c.name) + '</div>' +
        '<div class="cat-meta">' + c.laps + ' кр. · ' + (c.distance_km || 0) + ' км</div>' +
      '</div>' +
      '<div style="display:flex;align-items:center;gap:8px">' +
        '<div class="cat-count">' + (c.rider_count || 0) + '</div>' +
        '<div class="cat-actions">' +
          '<button class="btn btn-sm" onclick="event.stopPropagation();editCat(' + c.id + ')" title="Редакт.">✎</button>' +
          '<button class="btn btn-sm btn-danger" onclick="event.stopPropagation();deleteCat(' + c.id + ')" title="Удалить">✕</button>' +
        '</div>' +
      '</div>';
    list.appendChild(div);
    totalRiders += (c.rider_count || 0);
  });

  document.getElementById('cnt-all').textContent = totalRiders;
  if (!selectedCatId) allItem.classList.add('active');
}

function selectCategory(el, catId) {
  selectedCatId = catId;
  document.querySelectorAll('.cat-item').forEach(i => i.classList.remove('active'));
  el.classList.add('active');
  loadRiders();
}

function openCatModal(cat) {
  document.getElementById('cat-edit-id').value = cat ? cat.id : '';
  document.getElementById('cat-name').value = cat ? cat.name : '';
  document.getElementById('cat-laps').value = cat ? cat.laps : 5;
  document.getElementById('cat-dist').value = cat ? (cat.distance_km || 0) : 5;
  document.getElementById('cat-modal-title').innerHTML = cat
    ? '<span>Редактировать</span> категорию' : '<span>Новая</span> категория';
  document.getElementById('cat-modal').classList.add('open');
}
function closeCatModal() { document.getElementById('cat-modal').classList.remove('open'); }

async function saveCat() {
  const id = document.getElementById('cat-edit-id').value;
  const body = {
    name: document.getElementById('cat-name').value.trim(),
    laps: parseInt(document.getElementById('cat-laps').value) || 1,
    distance_km: parseFloat(document.getElementById('cat-dist').value) || 0,
  };
  if (!body.name) { toast('Введите название', true); return; }

  if (id) {
    await api('/api/categories/' + id, 'PUT', body);
    toast('Категория обновлена');
  } else {
    await api('/api/categories', 'POST', body);
    toast('Категория создана');
  }
  closeCatModal();
  loadAll();
}

async function editCat(catId) {
  const cat = categories.find(c => c.id === catId);
  if (cat) openCatModal(cat);
}

async function deleteCat(catId) {
  if (!confirm('Удалить категорию? Участники в ней не должны быть.')) return;
  const res = await api('/api/categories/' + catId, 'DELETE');
  if (res.error) { toast(res.error, true); return; }
  toast('Категория удалена');
  if (selectedCatId == catId) selectedCatId = '';
  loadAll();
}

function renderRiders() {
  const tbody = document.getElementById('riders-body');
  const query = document.getElementById('search-input').value.toLowerCase();
  const filtered = allRiders.filter(r => {
    if (!query) return true;
    return (String(r.number).includes(query) ||
            (r.last_name || '').toLowerCase().includes(query) ||
            (r.first_name || '').toLowerCase().includes(query) ||
            (r.club || '').toLowerCase().includes(query) ||
            (r.city || '').toLowerCase().includes(query) ||
            (r.epc || '').toLowerCase().includes(query));
  });

  document.getElementById('empty-state').style.display = filtered.length ? 'none' : 'flex';

  tbody.innerHTML = filtered.map(r => {
    const hasEpc = r.epc && r.epc.length > 0;
    return '<tr>' +
      '<td class="num-col">' + r.number + '</td>' +
      '<td style="font-weight:600">' + esc(r.last_name || '') + '</td>' +
      '<td>' + esc(r.first_name || '') + '</td>' +
      '<td class="c mono">' + (r.birth_year || '—') + '</td>' +
      '<td>' + esc(r.city || '') + '</td>' +
      '<td>' + esc(r.club || '') + '</td>' +
      '<td>' + esc(r.category_name || '—') + '</td>' +
      '<td class="epc-col' + (hasEpc ? ' bound' : '') + '" title="' + esc(r.epc || '') + '">' +
        (hasEpc ? r.epc : '—') + '</td>' +
      '<td><div class="actions-col">' +
        '<button class="btn btn-sm" onclick="editRider(' + r.id + ')" title="Редакт.">✎</button>' +
        '<button class="btn btn-sm btn-danger" onclick="deleteRider(' + r.id + ')" title="Удалить">✕</button>' +
      '</div></td>' +
    '</tr>';
  }).join('');
}

function applySearch() { renderRiders(); }

function updateStats() {
  const total = allRiders.length;
  const withEpc = allRiders.filter(r => r.epc && r.epc.length > 0).length;
  document.getElementById('stat-total').textContent = total;
  document.getElementById('stat-epc').textContent = withEpc;
  document.getElementById('stat-noepc').textContent = total - withEpc;
}

function openRiderModal(rider) {
  document.getElementById('rider-edit-id').value = rider ? rider.id : '';
  document.getElementById('r-number').value = rider ? rider.number : '';
  document.getElementById('r-lastname').value = rider ? (rider.last_name || '') : '';
  document.getElementById('r-firstname').value = rider ? (rider.first_name || '') : '';
  document.getElementById('r-year').value = rider ? (rider.birth_year || '') : '';
  document.getElementById('r-city').value = rider ? (rider.city || '') : '';
  document.getElementById('r-club').value = rider ? (rider.club || '') : '';
  document.getElementById('r-epc').value = rider ? (rider.epc || '') : '';
  document.getElementById('rider-modal-title').innerHTML = rider
    ? '<span>Редактировать</span> участника' : '<span>Новый</span> участник';

  const sel = document.getElementById('r-category');
  sel.innerHTML = '<option value="">— без категории —</option>';
  categories.forEach(c => {
    const o = document.createElement('option');
    o.value = c.id; o.textContent = c.name;
    if (rider && rider.category_id === c.id) o.selected = true;
    sel.appendChild(o);
  });
  if (!rider && selectedCatId) sel.value = selectedCatId;

  document.getElementById('rider-modal').classList.add('open');
}
function closeRiderModal() { document.getElementById('rider-modal').classList.remove('open'); }

async function saveRider() {
  const id = document.getElementById('rider-edit-id').value;
  const body = {
    number: parseInt(document.getElementById('r-number').value),
    last_name: document.getElementById('r-lastname').value.trim(),
    first_name: document.getElementById('r-firstname').value.trim(),
    birth_year: parseInt(document.getElementById('r-year').value) || null,
    city: document.getElementById('r-city').value.trim(),
    club: document.getElementById('r-club').value.trim(),
    category_id: parseInt(document.getElementById('r-category').value) || null,
    epc: document.getElementById('r-epc').value.trim() || null,
  };
  if (!body.number || !body.last_name) {
    toast('Номер и фамилия обязательны', true); return;
  }

  let res;
  if (id) {
    res = await api('/api/riders/' + id, 'PUT', body);
    if (res.error) { toast(res.error, true); return; }
    toast('Участник обновлён');
  } else {
    res = await api('/api/riders', 'POST', body);
    if (res.error) { toast(res.error, true); return; }
    toast('Участник добавлен');
  }
  closeRiderModal();
  loadAll();
}

async function editRider(riderId) {
  const rider = allRiders.find(r => r.id === riderId);
  if (rider) openRiderModal(rider);
}

async function deleteRider(riderId) {
  const rider = allRiders.find(r => r.id === riderId);
  const label = rider ? '#' + rider.number + ' ' + rider.last_name : '#' + riderId;
  if (!confirm('Удалить участника ' + label + '?')) return;
  const res = await api('/api/riders/' + riderId, 'DELETE');
  if (res.error) { toast(res.error, true); return; }
  toast('Участник удалён');
  loadAll();
}

function exportCSV() {
  window.location.href = '/api/riders/export';
}

async function importCSV(event) {
  const file = event.target.files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append('file', file);
  try {
    const resp = await fetch('/api/riders/import', { method: 'POST', body: formData });
    const res = await resp.json();
    if (res.error) { toast(res.error, true); return; }
    toast('Импортировано: ' + (res.imported || 0) + ' участников');
    loadAll();
  } catch (e) {
    toast('Ошибка импорта', true);
  }
  event.target.value = '';
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

loadAll();