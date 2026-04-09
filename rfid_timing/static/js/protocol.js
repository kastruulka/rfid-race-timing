async function api(url, method, body) {
  const opts = { method: method || 'GET' };
  if (body !== undefined) {
    opts.headers = { 'Content-Type': 'application/json' };
    opts.body = JSON.stringify(body);
  }
  return await fetch(url, opts);
}

function getSelectedCategoryId() {
  return parseInt(document.getElementById('p-category').value, 10) || null;
}

function ensureCategorySelected(categoryId) {
  if (categoryId) return true;
  alert('Выберите категорию');
  return false;
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function getConfig() {
  return {
    category_id: getSelectedCategoryId(),
    meta: {
      title: document.getElementById('p-title').value.trim(),
      subtitle: document.getElementById('p-subtitle').value.trim(),
      date: document.getElementById('p-date').value.trim(),
      location: document.getElementById('p-location').value.trim(),
      weather: document.getElementById('p-weather').value.trim(),
      chief_judge: document.getElementById('p-judge').value.trim(),
      secretary: document.getElementById('p-secretary').value.trim(),
    },
    columns: {
      place: document.getElementById('col-place').checked,
      number: document.getElementById('col-number').checked,
      name: document.getElementById('col-name').checked,
      birth_year: document.getElementById('col-birth_year').checked,
      club: document.getElementById('col-club').checked,
      city: document.getElementById('col-city').checked,
      start_time: document.getElementById('col-start_time').checked,
      time: document.getElementById('col-time').checked,
      gap: document.getElementById('col-gap').checked,
      warmup_lap: document.getElementById('col-warmup_lap').checked,
      laps: document.getElementById('col-laps').checked,
      speed: document.getElementById('col-speed').checked,
      status: document.getElementById('col-status').checked,
    },
  };
}

async function loadCategories() {
  const resp = await api('/api/categories', 'GET');
  const cats = await resp.json();
  const sel = document.getElementById('p-category');
  cats.forEach(c => {
    const o = document.createElement('option');
    o.value = c.id;
    o.textContent = c.name + ' (' + c.laps + ' кр.)';
    sel.appendChild(o);
  });
}

async function generatePreview() {
  const cfg = getConfig();
  if (!ensureCategorySelected(cfg.category_id)) return;

  const resp = await api('/api/protocol/preview', 'POST', cfg);
  const html = await resp.text();

  const scroll = document.getElementById('preview-scroll');
  const empty = document.getElementById('preview-empty');
  if (empty) empty.remove();

  let paper = scroll.querySelector('.preview-paper');
  if (!paper) {
    paper = document.createElement('div');
    paper.className = 'preview-paper';
    scroll.appendChild(paper);
  }
  paper.innerHTML = html;
}

async function downloadPDF() {
  const cfg = getConfig();
  if (!ensureCategorySelected(cfg.category_id)) return;

  const resp = await api('/api/protocol/pdf', 'POST', cfg);
  if (!resp.ok) {
    const err = await resp.json();
    alert(err.error || 'Ошибка генерации PDF');
    return;
  }
  const blob = await resp.blob();
  downloadBlob(blob, 'protocol.pdf');
}

loadCategories();
