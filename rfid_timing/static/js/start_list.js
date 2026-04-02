let allRiders = [];
let categories = [];
let selectedCatId = '';
let authManager = null;
const CURRENT_YEAR = new Date().getFullYear();
const MIN_BIRTH_YEAR = 1900;
const MAX_NUMBER = 99999;
const MAX_CATEGORY_LAPS = 1000;
const MAX_CATEGORY_DISTANCE = 1000;

function toast(msg, isError) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast show' + (isError ? ' error' : '');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.className = 'toast', 2500);
}

function validateCategoryForm(body) {
  if (!body.name) return 'Введите название';
  if (!Number.isInteger(body.laps) || body.laps < 1 || body.laps > MAX_CATEGORY_LAPS) {
    return 'Количество кругов должно быть от 1 до ' + MAX_CATEGORY_LAPS;
  }
  if (!Number.isFinite(body.distance_km) || body.distance_km < 0 || body.distance_km > MAX_CATEGORY_DISTANCE) {
    return 'Дистанция круга должна быть от 0 до ' + MAX_CATEGORY_DISTANCE + ' км';
  }
  return null;
}

function validateRiderForm(body) {
  if (!Number.isInteger(body.number) || body.number < 1 || body.number > MAX_NUMBER) {
    return 'Стартовый номер должен быть от 1 до ' + MAX_NUMBER;
  }
  if (!body.last_name) return 'Номер и фамилия обязательны';
  if (body.birth_year !== null) {
    if (!Number.isInteger(body.birth_year) || body.birth_year < MIN_BIRTH_YEAR || body.birth_year > CURRENT_YEAR) {
      return 'Год рождения должен быть в диапазоне ' + MIN_BIRTH_YEAR + '-' + CURRENT_YEAR;
    }
  }
  return null;
}

async function api(url, method, body) {
  const opts = { method: method || 'GET' };
  if (body !== undefined) {
    opts.headers = { 'Content-Type': 'application/json' };
    opts.body = JSON.stringify(body);
  }

  const result = await authManager.fetchJson(url, opts);
  if (result.unauthorized) return null;
  return result.data;
}

async function loadAll() {
  const data = await api('/api/categories', 'GET');
  categories = Array.isArray(data) ? data : [];
  renderCategories();
  await loadRiders();
}

async function loadRiders() {
  const qs = selectedCatId ? '?category_id=' + selectedCatId : '';
  const data = await api('/api/riders' + qs, 'GET');
  allRiders = Array.isArray(data) ? data : [];
  renderRiders();
  updateStats();
}

function renderCategories() {
  const list = document.getElementById('cat-list');
  const allItem = list.querySelector('[data-id=""]');
  list.innerHTML = '';
  list.appendChild(allItem);

  let totalRiders = 0;
  const canEdit = authManager && authManager.isAuthenticated();

  categories.forEach(c => {
    const warmupLabel = c.has_warmup_lap === false || c.has_warmup_lap === 0
      ? ' · без разгонного'
      : '';
    const div = document.createElement('div');
    div.className = 'cat-item' + (selectedCatId == c.id ? ' active' : '');
    div.dataset.id = c.id;
    div.onclick = () => selectCategory(div, c.id);
    div.innerHTML =
      '<div>' +
        '<div class="cat-name">' + esc(c.name) + '</div>' +
        '<div class="cat-meta">' + c.laps + ' кр. · ' + (c.distance_km || 0) + ' км' + warmupLabel + '</div>' +
      '</div>' +
      '<div style="display:flex;align-items:center;gap:8px">' +
        '<div class="cat-count">' + (c.rider_count || 0) + '</div>' +
        '<div class="cat-actions">' +
          '<button class="btn btn-sm" type="button" data-auth-required ' + (!canEdit ? 'disabled ' : '') + 'onclick="event.stopPropagation();editCat(' + c.id + ')" title="Редакт.">✎</button>' +
          '<button class="btn btn-sm btn-danger" type="button" data-auth-required ' + (!canEdit ? 'disabled ' : '') + 'onclick="event.stopPropagation();deleteCat(' + c.id + ')" title="Удалить">✕</button>' +
        '</div>' +
      '</div>';
    list.appendChild(div);
    totalRiders += (c.rider_count || 0);
  });

  document.getElementById('cnt-all').textContent = totalRiders;
  if (!selectedCatId) allItem.classList.add('active');
  if (authManager) authManager.syncProtectedControls();
}

function selectCategory(el, catId) {
  selectedCatId = catId;
  document.querySelectorAll('.cat-item').forEach(i => i.classList.remove('active'));
  el.classList.add('active');
  loadRiders();
}

async function openCatModal(cat) {
  if (!cat && !await authManager.requireAuth('Для добавления категории нужен пароль администратора')) return;
  if (cat && !authManager.isAuthenticated()) {
    authManager.openLogin('Для редактирования категории нужен пароль администратора');
    return;
  }

  document.getElementById('cat-edit-id').value = cat ? cat.id : '';
  document.getElementById('cat-name').value = cat ? cat.name : '';
  document.getElementById('cat-laps').value = cat ? cat.laps : 5;
  document.getElementById('cat-dist').value = cat ? (cat.distance_km || 0) : 5;
  document.getElementById('cat-has-warmup').checked = cat ? !(cat.has_warmup_lap === false || cat.has_warmup_lap === 0) : true;
  document.getElementById('cat-modal-title').innerHTML = cat
    ? '<span>Редактировать</span> категорию' : '<span>Новая</span> категория';
  document.getElementById('cat-modal').classList.add('open');
}
function closeCatModal() { document.getElementById('cat-modal').classList.remove('open'); }

async function saveCat() {
  if (!await authManager.requireAuth('Для сохранения категории нужен пароль администратора')) return;

  const id = document.getElementById('cat-edit-id').value;
  const body = {
    name: document.getElementById('cat-name').value.trim(),
    laps: parseInt(document.getElementById('cat-laps').value, 10) || 1,
    distance_km: parseFloat(document.getElementById('cat-dist').value) || 0,
    has_warmup_lap: document.getElementById('cat-has-warmup').checked,
  };
  const error = validateCategoryForm(body);
  if (error) { toast(error, true); return; }

  const res = id
    ? await api('/api/categories/' + id, 'PUT', body)
    : await api('/api/categories', 'POST', body);
  if (!res) return;

  if (res.error) {
    toast(res.error, true);
    return;
  }

  toast(id ? 'Категория обновлена' : 'Категория создана');
  closeCatModal();
  loadAll();
}

async function editCat(catId) {
  if (!await authManager.requireAuth('Для редактирования категории нужен пароль администратора')) return;
  const cat = categories.find(c => c.id === catId);
  if (cat) openCatModal(cat);
}

async function deleteCat(catId) {
  if (!await authManager.requireAuth('Для удаления категории нужен пароль администратора')) return;
  if (!confirm('Удалить категорию? Участники в ней не должны быть.')) return;
  const res = await api('/api/categories/' + catId, 'DELETE');
  if (!res) return;
  if (res.error) { toast(res.error, true); return; }
  toast('Категория удалена');
  if (selectedCatId == catId) selectedCatId = '';
  loadAll();
}

function renderRiders() {
  const tbody = document.getElementById('riders-body');
  const query = document.getElementById('search-input').value.toLowerCase();
  const canEdit = authManager && authManager.isAuthenticated();
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
        (hasEpc ? esc(r.epc) : '—') + '</td>' +
      '<td><div class="actions-col">' +
        '<button class="btn btn-sm" type="button" data-auth-required ' + (!canEdit ? 'disabled ' : '') + 'onclick="editRider(' + r.id + ')" title="Редакт.">✎</button>' +
        '<button class="btn btn-sm btn-danger" type="button" data-auth-required ' + (!canEdit ? 'disabled ' : '') + 'onclick="deleteRider(' + r.id + ')" title="Удалить">✕</button>' +
      '</div></td>' +
    '</tr>';
  }).join('');

  if (authManager) authManager.syncProtectedControls();
}

function applySearch() { renderRiders(); }

function updateStats() {
  const total = allRiders.length;
  const withEpc = allRiders.filter(r => r.epc && r.epc.length > 0).length;
  document.getElementById('stat-total').textContent = total;
  document.getElementById('stat-epc').textContent = withEpc;
  document.getElementById('stat-noepc').textContent = total - withEpc;
}

async function openRiderModal(rider) {
  const reason = rider
    ? 'Для редактирования участника нужен пароль администратора'
    : 'Для добавления участника нужен пароль администратора';
  if (!await authManager.requireAuth(reason)) return;

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
    o.value = c.id;
    o.textContent = c.name;
    if (rider && rider.category_id === c.id) o.selected = true;
    sel.appendChild(o);
  });
  if (!rider && selectedCatId) sel.value = selectedCatId;

  document.getElementById('rider-modal').classList.add('open');
}
function closeRiderModal() { document.getElementById('rider-modal').classList.remove('open'); }

async function saveRider() {
  if (!await authManager.requireAuth('Для сохранения участника нужен пароль администратора')) return;

  const id = document.getElementById('rider-edit-id').value;
  const body = {
    number: parseInt(document.getElementById('r-number').value, 10),
    last_name: document.getElementById('r-lastname').value.trim(),
    first_name: document.getElementById('r-firstname').value.trim(),
    birth_year: parseInt(document.getElementById('r-year').value, 10) || null,
    city: document.getElementById('r-city').value.trim(),
    club: document.getElementById('r-club').value.trim(),
    category_id: parseInt(document.getElementById('r-category').value, 10) || null,
    epc: document.getElementById('r-epc').value.trim() || null,
  };
  const error = validateRiderForm(body);
  if (error) { toast(error, true); return; }

  const res = id
    ? await api('/api/riders/' + id, 'PUT', body)
    : await api('/api/riders', 'POST', body);
  if (!res) return;
  if (res.error) { toast(res.error, true); return; }

  toast(id ? 'Участник обновлён' : 'Участник добавлен');
  closeRiderModal();
  loadAll();
}

async function editRider(riderId) {
  if (!await authManager.requireAuth('Для редактирования участника нужен пароль администратора')) return;
  const rider = allRiders.find(r => r.id === riderId);
  if (rider) openRiderModal(rider);
}

async function deleteRider(riderId) {
  if (!await authManager.requireAuth('Для удаления участника нужен пароль администратора')) return;
  const rider = allRiders.find(r => r.id === riderId);
  const label = rider ? '#' + rider.number + ' ' + rider.last_name : '#' + riderId;
  if (!confirm('Удалить участника ' + label + '?')) return;
  const res = await api('/api/riders/' + riderId, 'DELETE');
  if (!res) return;
  if (res.error) { toast(res.error, true); return; }
  toast('Участник удалён');
  loadAll();
}

function exportCSV() {
  window.location.href = '/api/riders/export';
}

async function triggerImport() {
  if (!await authManager.requireAuth('Для импорта нужен пароль администратора')) return;
  document.getElementById('csv-import-input').click();
}

async function importCSV(event) {
  if (!authManager.isAuthenticated()) {
    authManager.openLogin('Для импорта нужен пароль администратора');
    event.target.value = '';
    return;
  }

  const file = event.target.files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append('file', file);
  try {
    const resp = await fetch('/api/riders/import', {
      method: 'POST',
      credentials: 'same-origin',
      body: formData,
    });
    const res = await resp.json();
    if (resp.status === 401) {
      await authManager.handleUnauthorized('Сессия истекла. Войдите заново для импорта');
      return;
    }
    if (res.error) { toast(res.error, true); return; }
    if (res.errors && res.errors.length) { toast(res.errors.join('; '), true); return; }
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

function bindModalClose(id) {
  const modal = document.getElementById(id);
  modal.addEventListener('click', function (event) {
    if (event.target === modal) modal.classList.remove('open');
  });
}

async function init() {
  authManager = createAuthManager({
    toast: toast,
    authHintId: 'auth-hint',
    logoutButtonId: 'logout-btn',
    onAuthChange: function () {
      renderCategories();
      renderRiders();
    },
  });

  bindModalClose('cat-modal');
  bindModalClose('rider-modal');
  document.getElementById('r-year').setAttribute('max', String(CURRENT_YEAR));

  await authManager.checkAuth();
  await loadAll();
}

init();
