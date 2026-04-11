(function () {
  const page = window.StartListPage || (window.StartListPage = {});

  page.toast = window.showToast;
  page.constants = {
    CURRENT_YEAR: new Date().getFullYear(),
    MIN_BIRTH_YEAR: 1900,
    MAX_NUMBER: 99999,
    MAX_CATEGORY_LAPS: 1000,
    MAX_CATEGORY_DISTANCE: 1000,
  };

  page.state = {
    categories: [],
    riders: [],
    selectedCatId: '',
    tagScannerTimer: null,
    tagScannerLastHash: '',
  };

  page.els = {
    authHint: document.getElementById('auth-hint'),
    categoryAddBtn: document.getElementById('btn-add-category'),
    categoryList: document.getElementById('cat-list'),
    allCount: document.getElementById('cnt-all'),
    categoryModal: document.getElementById('cat-modal'),
    categoryModalTitle: document.getElementById('cat-modal-title'),
    categoryEditId: document.getElementById('cat-edit-id'),
    categoryName: document.getElementById('cat-name'),
    categoryLaps: document.getElementById('cat-laps'),
    categoryDistance: document.getElementById('cat-dist'),
    categoryWarmup: document.getElementById('cat-has-warmup'),
    categoryCancelBtn: document.getElementById('btn-close-cat-modal'),
    categorySaveBtn: document.getElementById('btn-save-category'),
    searchInput: document.getElementById('search-input'),
    riderAddBtn: document.getElementById('btn-add-rider'),
    exportBtn: document.getElementById('btn-export-csv'),
    importBtn: document.getElementById('btn-trigger-import'),
    csvImportInput: document.getElementById('csv-import-input'),
    statTotal: document.getElementById('stat-total'),
    statEpc: document.getElementById('stat-epc'),
    statNoEpc: document.getElementById('stat-noepc'),
    ridersBody: document.getElementById('riders-body'),
    emptyState: document.getElementById('empty-state'),
    riderModal: document.getElementById('rider-modal'),
    riderModalTitle: document.getElementById('rider-modal-title'),
    riderEditId: document.getElementById('rider-edit-id'),
    riderNumber: document.getElementById('r-number'),
    riderCategory: document.getElementById('r-category'),
    riderLastName: document.getElementById('r-lastname'),
    riderFirstName: document.getElementById('r-firstname'),
    riderBirthYear: document.getElementById('r-year'),
    riderCity: document.getElementById('r-city'),
    riderClub: document.getElementById('r-club'),
    riderEpc: document.getElementById('r-epc'),
    openTagScannerBtn: document.getElementById('btn-open-tag-scanner'),
    riderCancelBtn: document.getElementById('btn-close-rider-modal'),
    riderSaveBtn: document.getElementById('btn-save-rider'),
    tagScannerModal: document.getElementById('tag-scanner-modal'),
    tagScannerStatus: document.getElementById('tag-scanner-status'),
    tagScannerList: document.getElementById('tag-scanner-list'),
    tagScannerCloseBtn: document.getElementById('btn-close-tag-scanner'),
  };

  page.getResponseData = function getResponseData(result) {
    if (!result || result.unauthorized) return null;
    return result.data;
  };

  page.getApiError = function getApiError(result, fallback) {
    const data = page.getResponseData(result);
    if (!data) return fallback || 'Ошибка';
    if (Array.isArray(data.errors) && data.errors.length) {
      return data.errors.join('; ');
    }
    return data.error || fallback || null;
  };

  page.handleApiError = function handleApiError(result, fallback) {
    const message = page.getApiError(result, fallback);
    if (!message) return false;
    page.toast(message, true);
    return true;
  };

  page.fetchCollection = async function fetchCollection(url) {
    const result = await page.http.fetchJson(url);
    const data = page.getResponseData(result);
    return Array.isArray(data) ? data : [];
  };

  page.ensureAuthenticated = async function ensureAuthenticated(reason) {
    if (page.authManager && page.authManager.state.authenticated) return true;
    await page.authManager.login({ reason: reason, silent: true });
    return false;
  };

  page.loadCategories = async function loadCategories() {
    page.state.categories = await page.fetchCollection('/api/categories');
    page.categories.renderCategories();
  };

  page.loadRiders = async function loadRiders() {
    const suffix = page.state.selectedCatId ? '?category_id=' + page.state.selectedCatId : '';
    page.state.riders = await page.fetchCollection('/api/riders' + suffix);
    page.riders.renderRiders();
    page.riders.updateStats();
  };

  page.loadInitialData = async function loadInitialData() {
    await page.loadCategories();
    await page.loadRiders();
  };

  page.initAuth = function initAuth() {
    page.authManager = createAuthManager({
      toast: page.toast,
      authHintId: 'auth-hint',
      logoutButtonId: 'logout-btn',
      onAuthChange: function () {
        page.categories.renderCategories();
        page.riders.renderRiders();
      },
    });
    page.http = createAuthHttpClient({ authManager: page.authManager });
  };

  page.bindModalClose = function bindModalClose(modal, onClose) {
    modal.addEventListener('click', function (event) {
      if (event.target === modal) {
        onClose();
      }
    });
  };

  page.bindUi = function bindUi() {
    const categoryActionHandlers = {
      'edit-category': function (button) {
        page.categories.editCat(button.dataset.categoryId);
      },
      'delete-category': function (button) {
        page.categories.deleteCat(button.dataset.categoryId);
      },
    };
    const riderActionHandlers = {
      'edit-rider': function (button) {
        page.riders.editRider(button.dataset.riderId);
      },
      'delete-rider': function (button) {
        page.riders.deleteRider(button.dataset.riderId);
      },
    };

    page.els.categoryAddBtn.addEventListener('click', function () {
      page.categories.openCatModal();
    });
    page.els.categoryCancelBtn.addEventListener('click', page.categories.closeCatModal);
    page.els.categorySaveBtn.addEventListener('click', page.categories.saveCat);

    page.els.categoryList.addEventListener('click', function (event) {
      const actionButton = event.target.closest('[data-action]');
      if (actionButton && categoryActionHandlers[actionButton.dataset.action]) {
        event.stopPropagation();
        categoryActionHandlers[actionButton.dataset.action](actionButton);
        return;
      }

      const item = event.target.closest('.cat-item');
      if (!item) return;
      page.categories.selectCategory(item.dataset.categoryId || '');
    });

    page.els.searchInput.addEventListener('input', page.riders.applySearch);
    page.els.riderAddBtn.addEventListener('click', function () {
      page.riders.openRiderModal();
    });
    page.els.exportBtn.addEventListener('click', page.importExport.exportCSV);
    page.els.importBtn.addEventListener('click', page.importExport.triggerImport);
    page.els.csvImportInput.addEventListener('change', page.importExport.importCSV);
    page.els.riderCancelBtn.addEventListener('click', page.riders.closeRiderModal);
    page.els.riderSaveBtn.addEventListener('click', page.riders.saveRider);
    page.els.openTagScannerBtn.addEventListener('click', page.tagScanner.openTagScanner);
    page.els.tagScannerCloseBtn.addEventListener('click', page.tagScanner.closeTagScanner);

    page.els.ridersBody.addEventListener('click', function (event) {
      const button = event.target.closest('[data-action]');
      if (!button || !riderActionHandlers[button.dataset.action]) return;
      riderActionHandlers[button.dataset.action](button);
    });

    page.els.tagScannerList.addEventListener('click', function (event) {
      const button = event.target.closest('[data-action="use-tag"]');
      if (!button) return;
      page.tagScanner.useScannedTag(button.dataset.epc || '');
    });

    page.bindModalClose(page.els.categoryModal, page.categories.closeCatModal);
    page.bindModalClose(page.els.riderModal, page.riders.closeRiderModal);
    page.bindModalClose(page.els.tagScannerModal, page.tagScanner.closeTagScanner);
  };

  page.initFormConstraints = function initFormConstraints() {
    page.els.riderBirthYear.setAttribute('max', String(page.constants.CURRENT_YEAR));
  };

  page.init = async function init() {
    page.initAuth();
    page.bindUi();
    page.initFormConstraints();
    try {
      await page.authManager.checkAuth();
      await page.loadInitialData();
    } finally {
      window.pageHydration.finish();
    }
  };

  page.init();
})();
