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
const protocolState = window.ProtocolState;
const protocolScope = window.createProtocolScope({
  els: els,
  getCategories: function getCategories() {
    return categoriesCache;
  },
  setCategories: function setCategories(categories) {
    categoriesCache = categories;
  },
  protocolState: protocolState,
  toast: toast,
});

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
    scope: protocolScope.getScope(),
    category_id: protocolScope.getSelectedCategoryId(),
    category_ids: protocolScope.getSelectedCategoryIds(),
    meta: getProtocolMeta(),
    columns: getProtocolColumns(),
  };
}

const protocolActions = window.createProtocolActions({
  els: els,
  getProtocolRequestBody: getProtocolRequestBody,
  protocolScope: protocolScope,
  toast: toast,
});

function bindUi() {
  els.generatePreviewButton.addEventListener('click', protocolActions.generatePreview);
  els.downloadPdfButton.addEventListener('click', protocolActions.downloadPDF);
  if (els.downloadSyncButton) {
    els.downloadSyncButton.addEventListener('click', protocolActions.downloadSync);
  }
  if (els.scope) {
    els.scope.addEventListener('change', protocolScope.updateScopeUi);
  }
  if (els.category) {
    els.category.addEventListener('change', function () {
      protocolState.saveState({ category_id: protocolScope.getSelectedCategoryId() });
    });
  }
  if (els.selectAllCategoriesButton) {
    els.selectAllCategoriesButton.addEventListener('click', function () {
      protocolScope.toggleAllCategoryChecks(true);
    });
  }
  if (els.clearAllCategoriesButton) {
    els.clearAllCategoriesButton.addEventListener('click', function () {
      protocolScope.toggleAllCategoryChecks(false);
    });
  }
}

async function init() {
  const savedState = protocolState.loadSavedState();
  if (els.scope && savedState.scope) {
    els.scope.value = savedState.scope;
  }
  bindUi();
  await protocolScope.loadCategories();
}

init();
