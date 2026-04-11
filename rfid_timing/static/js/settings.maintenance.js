(function () {
  const page = window.SettingsPage || (window.SettingsPage = {});
  const toast = window.showToast;

  page.loadSysInfo = async function loadSysInfo() {
    try {
      const result = await page.http.fetchJson('/api/settings/sys-info');
      const info = result.data;
      if (!info) return;

      page.els.sysDb.textContent = info.db_size;
      page.els.sysLog.textContent = info.log_size;
      page.els.sysBackups.textContent = info.backups_count;
      page.els.sysRace.textContent = info.race_id || '—';
      page.els.sysRiders.textContent = info.riders_count;
    } catch {
      // ignore
    }
  };

  page.backupDB = async function backupDB() {
    try {
      const result = await page.http.fetchJson('/api/settings/backup', { method: 'POST' });
      const data = result.data;
      if (!data) return;

      if (data.ok) {
        toast('Бэкап создан: ' + data.filename);
      } else {
        toast(data.error || 'Ошибка', true);
      }
    } catch {
      toast('Ошибка создания бэкапа', true);
    }
  };

  page.resetRace = async function resetRace() {
    if (
      !confirm(
        'Сбросить текущую гонку? Будет создана новая сессия.\nСтарые данные сохранятся в архиве БД.'
      )
    )
      return;

    try {
      const result = await page.http.fetchJson('/api/settings/reset-race', { method: 'POST' });
      const data = result.data;
      if (!data) return;

      if (data.ok) {
        toast('Новая гоночная сессия: #' + data.race_id);
      } else {
        toast(data.error || 'Ошибка', true);
      }
    } catch {
      toast('Ошибка сброса', true);
    }
  };
})();
