const toast = window.showToast;

const els = {
  scope: document.getElementById('p-scope'),
  category: document.getElementById('p-category'),
  categorySingleWrap: document.getElementById('p-category-single-wrap'),
  categoryMultiWrap: document.getElementById('p-category-multi-wrap'),
  categoryMulti: document.getElementById('p-category-multi'),
  selectAllCategoriesButton: document.getElementById('btn-select-all-categories'),
  clearAllCategoriesButton: document.getElementById('btn-clear-all-categories'),
  title: document.getElementById('p-title'),
  subtitle: document.getElementById('p-subtitle'),
  date: document.getElementById('p-date'),
  location: document.getElementById('p-location'),
  weather: document.getElementById('p-weather'),
  chiefJudge: document.getElementById('p-judge'),
  secretary: document.getElementById('p-secretary'),
  colPlace: document.getElementById('col-place'),
  colNumber: document.getElementById('col-number'),
  colName: document.getElementById('col-name'),
  colBirthYear: document.getElementById('col-birth_year'),
  colClub: document.getElementById('col-club'),
  colCity: document.getElementById('col-city'),
  colStartTime: document.getElementById('col-start_time'),
  colTime: document.getElementById('col-time'),
  colGap: document.getElementById('col-gap'),
  colWarmupLap: document.getElementById('col-warmup_lap'),
  colLaps: document.getElementById('col-laps'),
  colSpeed: document.getElementById('col-speed'),
  colStatus: document.getElementById('col-status'),
  previewScroll: document.getElementById('preview-scroll'),
  previewEmpty: document.getElementById('preview-empty'),
  generatePreviewButton: document.getElementById('btn-generate-preview'),
  downloadPdfButton: document.getElementById('btn-download-pdf'),
  downloadSyncButton: document.getElementById('btn-download-sync'),
};

let categoriesCache = [];
const STORAGE_KEY = 'rfid-protocol-form';

function loadSavedState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function saveState(patch) {
  const current = loadSavedState();
  const next = Object.assign({}, current, patch);
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    return;
  }
}

function getScope() {
  return (els.scope && els.scope.value) || 'single';
}

function getSelectedCategoryId() {
  return parseInt(els.category.value, 10) || null;
}

function getSelectedCategoryIds() {
  if (!els.categoryMulti) return [];
  return Array.from(els.categoryMulti.querySelectorAll('input[type="checkbox"]:checked')).map(
    function (input) {
      return parseInt(input.value, 10);
    }
  );
}

function getSelectedCategoryOption() {
  return els.category.options[els.category.selectedIndex] || null;
}

function getSelectedCategoryNames() {
  const scope = getScope();
  if (scope === 'all') {
    return categoriesCache.map(function (category) {
      return category.name;
    });
  }

  if (scope === 'selected') {
    const selectedIds = new Set(getSelectedCategoryIds());
    return categoriesCache
      .filter(function (category) {
        return selectedIds.has(Number(category.id));
      })
      .map(function (category) {
        return category.name;
      });
  }

  const option = getSelectedCategoryOption();
  if (!option || !option.value) return [];
  return [option.textContent.replace(/\s*\(.*/, '').trim()];
}

function getProtocolMeta() {
  return {
    title: els.title.value.trim(),
    subtitle: els.subtitle.value.trim(),
    date: els.date.value.trim(),
    location: els.location.value.trim(),
    weather: els.weather.value.trim(),
    chief_judge: els.chiefJudge.value.trim(),
    secretary: els.secretary.value.trim(),
  };
}

function getProtocolColumns() {
  return {
    place: els.colPlace.checked,
    number: els.colNumber.checked,
    name: els.colName.checked,
    birth_year: els.colBirthYear.checked,
    club: els.colClub.checked,
    city: els.colCity.checked,
    start_time: els.colStartTime.checked,
    time: els.colTime.checked,
    gap: els.colGap.checked,
    warmup_lap: els.colWarmupLap.checked,
    laps: els.colLaps.checked,
    speed: els.colSpeed.checked,
    status: els.colStatus.checked,
  };
}

function getProtocolRequestBody() {
  return {
    scope: getScope(),
    category_id: getSelectedCategoryId(),
    category_ids: getSelectedCategoryIds(),
    meta: getProtocolMeta(),
    columns: getProtocolColumns(),
  };
}

function ensureCategorySelection(body) {
  if (body.scope === 'all') return true;
  if (body.scope === 'selected') {
    if (body.category_ids.length > 0) return true;
    toast('Выберите хотя бы одну категорию', true);
    return false;
  }
  if (body.category_id) return true;
  toast('Выберите категорию', true);
  return false;
}

function renderPreview(html) {
  if (els.previewEmpty) {
    els.previewEmpty.remove();
    els.previewEmpty = null;
  }

  let paper = els.previewScroll.querySelector('.preview-paper');
  if (!paper) {
    paper = document.createElement('div');
    paper.className = 'preview-paper';
    els.previewScroll.appendChild(paper);
  }

  paper.innerHTML = html;
}

function getErrorMessage(result, fallback) {
  const data = result && result.data;
  if (data && typeof data === 'object' && data.error) return data.error;
  return fallback || 'Ошибка запроса';
}

function sanitizeFilenamePart(value, replacement) {
  return String(value || '')
    .split('')
    .map(function (char) {
      if (char.charCodeAt(0) < 32 || /[<>:"/\\|?*]/.test(char)) {
        return replacement;
      }
      return char;
    })
    .join('');
}

function buildScopeFilenamePrefix() {
  const scope = getScope();
  if (scope === 'all') return 'all-categories';

  const categoryNames = getSelectedCategoryNames();
  if (scope === 'selected') {
    if (categoryNames.length === 1) return categoryNames[0];
    return 'selected-categories-' + categoryNames.length;
  }

  return categoryNames[0] || 'protocol';
}

function buildPdfFilename() {
  const prefix = sanitizeFilenamePart(buildScopeFilenamePrefix(), '_');
  const dateLabel = els.date.value.trim() || new Date().toISOString().slice(0, 10);
  const safeDate = sanitizeFilenamePart(dateLabel, '-');
  return prefix + '-' + safeDate + '.pdf';
}

function buildSyncFilename() {
  const prefix = sanitizeFilenamePart(buildScopeFilenamePrefix(), '_');
  const dateLabel = els.date.value.trim() || new Date().toISOString().slice(0, 10);
  const safeDate = sanitizeFilenamePart(dateLabel, '-');
  return prefix + '-' + safeDate + '.json';
}

function formatCategoryLabel(category) {
  if (category && category.finish_mode === 'time' && category.time_limit_sec) {
    return category.name + ' (' + category.time_limit_sec + ' сек)';
  }
  return category.name + ' (' + category.laps + ' кр.)';
}

function createCategoryPickItem(category, checked) {
  const label = document.createElement('label');
  label.className = 'cb-item category-pick-item';

  const input = document.createElement('input');
  input.type = 'checkbox';
  input.value = String(category.id);
  input.checked = checked;
  input.addEventListener('change', function () {
    saveState({ category_ids: getSelectedCategoryIds() });
  });

  const text = document.createElement('span');
  text.className = 'category-pick-label';
  text.textContent = formatCategoryLabel(category);

  label.appendChild(input);
  label.appendChild(text);
  return label;
}

function populateMultiCategoryList(categories, selectedIds) {
  if (!els.categoryMulti) return;
  const selectedIdSet = new Set(selectedIds.map(String));
  els.categoryMulti.innerHTML = '';

  categories.forEach(function (category) {
    const isChecked = selectedIdSet.has(String(category.id));
    els.categoryMulti.appendChild(createCategoryPickItem(category, isChecked));
  });
}

function updateScopeUi() {
  const scope = getScope();
  const singleVisible = scope === 'single';
  const multiVisible = scope === 'selected';

  if (els.categorySingleWrap) {
    els.categorySingleWrap.classList.toggle('hidden', !singleVisible);
  }
  if (els.categoryMultiWrap) {
    els.categoryMultiWrap.classList.toggle('hidden', !multiVisible);
  }
  saveState({ scope: scope });
}

function toggleAllCategoryChecks(checked) {
  if (!els.categoryMulti) return;
  els.categoryMulti.querySelectorAll('input[type="checkbox"]').forEach(function (input) {
    input.checked = checked;
  });
  saveState({ category_ids: getSelectedCategoryIds() });
}

async function loadCategories() {
  const result = await window.httpClient.fetchJson('/api/categories');
  const categories = Array.isArray(result.data) ? result.data : [];
  categoriesCache = categories;
  const savedState = loadSavedState();

  const selectedSingleValue = els.category.value || String(savedState.category_id || '');
  const selectedMultiValues = (
    getSelectedCategoryIds().length ? getSelectedCategoryIds() : savedState.category_ids || []
  ).map(String);

  els.category.innerHTML = '';

  const placeholder = document.createElement('option');
  placeholder.value = '';
  placeholder.textContent = '-- Выберите категорию --';
  els.category.appendChild(placeholder);

  categories.forEach(function (category) {
    const option = document.createElement('option');
    option.value = category.id;
    option.textContent = formatCategoryLabel(category);
    els.category.appendChild(option);
  });

  if (
    selectedSingleValue &&
    categories.some(function (category) {
      return String(category.id) === String(selectedSingleValue);
    })
  ) {
    els.category.value = selectedSingleValue;
  }

  populateMultiCategoryList(categories, selectedMultiValues);
  updateScopeUi();
}

async function generatePreview() {
  const body = getProtocolRequestBody();
  if (!ensureCategorySelection(body)) return;

  try {
    const result = await window.httpClient.fetchText('/api/protocol/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!result.ok) {
      toast(getErrorMessage(result, 'Ошибка генерации предпросмотра'), true);
      return;
    }

    renderPreview(result.data || '');
  } catch {
    toast('Ошибка сети при загрузке предпросмотра', true);
  }
}

async function downloadPDF() {
  const body = getProtocolRequestBody();
  if (!ensureCategorySelection(body)) return;

  try {
    const result = await window.httpClient.fetchBlob('/api/protocol/pdf', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!result.ok) {
      toast(getErrorMessage(result, 'Ошибка генерации PDF'), true);
      return;
    }

    window.downloadBlob(result.data, buildPdfFilename());
  } catch {
    toast('Ошибка сети при загрузке PDF', true);
  }
}

async function downloadSync() {
  const body = getProtocolRequestBody();
  if (!ensureCategorySelection(body)) return;

  try {
    const result = await window.httpClient.fetchBlob('/api/protocol/sync-export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!result.ok) {
      toast(getErrorMessage(result, 'Ошибка экспорта JSON Sync'), true);
      return;
    }

    window.downloadBlob(result.data, buildSyncFilename());
  } catch {
    toast('Ошибка сети при загрузке JSON Sync', true);
  }
}

function bindUi() {
  els.generatePreviewButton.addEventListener('click', generatePreview);
  els.downloadPdfButton.addEventListener('click', downloadPDF);
  if (els.downloadSyncButton) {
    els.downloadSyncButton.addEventListener('click', downloadSync);
  }
  if (els.scope) {
    els.scope.addEventListener('change', updateScopeUi);
  }
  if (els.category) {
    els.category.addEventListener('change', function () {
      saveState({ category_id: getSelectedCategoryId() });
    });
  }
  if (els.selectAllCategoriesButton) {
    els.selectAllCategoriesButton.addEventListener('click', function () {
      toggleAllCategoryChecks(true);
    });
  }
  if (els.clearAllCategoriesButton) {
    els.clearAllCategoriesButton.addEventListener('click', function () {
      toggleAllCategoryChecks(false);
    });
  }
}

async function init() {
  const savedState = loadSavedState();
  if (els.scope && savedState.scope) {
    els.scope.value = savedState.scope;
  }
  bindUi();
  await loadCategories();
}

init();
