(function () {
  const page = window.SettingsPage || (window.SettingsPage = {});
  const toast = window.showToast;

  page.loadSettings = async function loadSettings() {
    const result = await page.http.fetchJson('/api/settings');
    if (!result.data) return;

    page.writeSettingsForm(result.data);
    page.updateModeVisibility();
    page.loadSysInfo();
  };

  page.saveSettings = async function saveSettings() {
    const result = await page.http.fetchJson('/api/settings/apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(page.getSettingsPayload()),
    });
    const data = result.data;
    if (!data) return;

    if (data.ok) {
      toast(data.message || 'Настройки применены');
      page.loadReaderStatus();
      return;
    }

    const msg = data.errors ? 'Ошибки: ' + data.errors.join('; ') : data.error || 'Ошибка';
    toast(msg, true);
  };

  page.checkConnection = async function checkConnection() {
    page.setStatusBadge(page.els.connectionBadge, 'wait', 'Проверяю…');

    try {
      const result = await page.http.fetchJson('/api/settings/check-reader', { method: 'POST' });
      const data = result.data;
      if (!data) {
        page.setStatusBadge(page.els.connectionBadge, 'err', '—');
        return;
      }

      if (data.ok) {
        page.setStatusBadge(
          page.els.connectionBadge,
          'ok',
          data.message || 'Подключён',
          data.message || ''
        );
      } else {
        page.setStatusBadge(page.els.connectionBadge, 'err', 'Нет связи', data.error || '');
        toast(data.error || 'Нет связи', true);
      }
    } catch {
      page.setStatusBadge(page.els.connectionBadge, 'err', 'Ошибка сети');
    }
  };

  page.withAdminAuth = async function withAdminAuth(message, fn) {
    if (page.authManager && page.authManager.state.authenticated) {
      return await fn();
    }

    const ok = await page.authManager.login({ reason: message, silent: true });
    if (!ok) return null;
    return await fn();
  };
})();
