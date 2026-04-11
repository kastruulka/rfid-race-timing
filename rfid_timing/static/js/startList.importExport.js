(function () {
  const page = window.StartListPage || (window.StartListPage = {});

  function exportCSV() {
    window.location.href = '/api/riders/export';
  }

  async function triggerImport() {
    if (!(await page.ensureAuthenticated('Для импорта нужен пароль администратора'))) return;
    page.els.csvImportInput.click();
  }

  async function importCSV(event) {
    const file = event.target.files && event.target.files[0];
    if (!file) return;

    if (!(await page.ensureAuthenticated('Для импорта нужен пароль администратора'))) {
      event.target.value = '';
      return;
    }

    const formData = new FormData();
    formData.append('file', file);

    try {
      const result = await page.http.fetchJson('/api/riders/import', {
        method: 'POST',
        body: formData,
        unauthorizedMessage: 'Сессия истекла. Войдите заново для импорта',
      });
      const data = page.getResponseData(result);
      if (page.handleApiError(result)) return;

      page.toast('Импортировано: ' + String(data.imported || 0) + ' участников');
      await page.loadInitialData();
    } catch {
      page.toast('Ошибка импорта', true);
    } finally {
      event.target.value = '';
    }
  }

  page.importExport = {
    exportCSV: exportCSV,
    triggerImport: triggerImport,
    importCSV: importCSV,
  };
})();
