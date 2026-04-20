const toast = window.showToast;

const els = {
  category: document.getElementById('p-category'),
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
};

function getSelectedCategoryId() {
  return parseInt(els.category.value, 10) || null;
}

function getSelectedCategoryOption() {
  return els.category.options[els.category.selectedIndex] || null;
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
    category_id: getSelectedCategoryId(),
    meta: getProtocolMeta(),
    columns: getProtocolColumns(),
  };
}

function ensureCategorySelected(categoryId) {
  if (categoryId) return true;
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

function buildPdfFilename() {
  const option = getSelectedCategoryOption();
  const categoryLabel =
    option && option.value ? option.textContent.replace(/\s*\(.*/, '').trim() : 'protocol';
  const dateLabel = els.date.value.trim() || new Date().toISOString().slice(0, 10);
  const safeCategory = sanitizeFilenamePart(categoryLabel, '_');
  const safeDate = sanitizeFilenamePart(dateLabel, '-');
  return safeCategory + '-' + safeDate + '.pdf';
}

function formatCategoryLabel(category) {
  if (category && category.finish_mode === 'time' && category.time_limit_sec) {
    return category.name + ' (' + category.time_limit_sec + ' сек)';
  }
  return category.name + ' (' + category.laps + ' кр.)';
}

async function loadCategories() {
  const result = await window.httpClient.fetchJson('/api/categories');
  const cats = Array.isArray(result.data) ? result.data : [];
  const selectedValue = els.category.value;

  els.category.innerHTML = '';

  const placeholder = document.createElement('option');
  placeholder.value = '';
  placeholder.textContent = '-- Выберите категорию --';
  els.category.appendChild(placeholder);

  cats.forEach(function (category) {
    const option = document.createElement('option');
    option.value = category.id;
    option.textContent = formatCategoryLabel(category);
    els.category.appendChild(option);
  });

  if (
    selectedValue &&
    cats.some(function (category) {
      return String(category.id) === String(selectedValue);
    })
  ) {
    els.category.value = selectedValue;
  }
}

async function generatePreview() {
  const body = getProtocolRequestBody();
  if (!ensureCategorySelected(body.category_id)) return;

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
  if (!ensureCategorySelected(body.category_id)) return;

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

function bindUi() {
  els.generatePreviewButton.addEventListener('click', generatePreview);
  els.downloadPdfButton.addEventListener('click', downloadPDF);
}

async function init() {
  bindUi();
  await loadCategories();
}

init();
