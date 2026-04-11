(function () {
  const page = window.SettingsPage || (window.SettingsPage = {});
  const toast = window.showToast;

  page.bindEvents = function bindEvents() {
    page.els.useEmulator.addEventListener('change', page.updateModeVisibility);
    page.els.saveSettingsButton.addEventListener('click', function () {
      page.withAdminAuth('Для сохранения настроек нужен пароль администратора', page.saveSettings);
    });
    page.els.checkConnectionButton.addEventListener('click', function () {
      page.withAdminAuth(
        'Для проверки подключения нужен пароль администратора',
        page.checkConnection
      );
    });
    page.els.backupDbButton.addEventListener('click', function () {
      page.withAdminAuth('Для резервной копии нужен пароль администратора', page.backupDB);
    });
    page.els.resetRaceButton.addEventListener('click', function () {
      page.withAdminAuth('Для сброса гонки нужен пароль администратора', page.resetRace);
    });
  };

  page.init = async function init() {
    page.authManager = createAuthManager({
      toast: toast,
      authHintId: 'auth-hint',
      logoutButtonId: 'logout-btn',
      onAuthChange: function (authenticated) {
        if (authenticated) {
          Promise.all([page.loadSettings(), page.loadReaderStatus()]).finally(function () {
            window.pageHydration.finish();
          });
          return;
        }

        page.updateModeVisibility();
        window.pageHydration.finish();
      },
    });
    page.http = createAuthHttpClient({ authManager: page.authManager });

    page.bindEvents();

    try {
      await page.authManager.checkAuth();
      await Promise.all([page.loadSettings(), page.loadReaderStatus()]);
    } finally {
      window.pageHydration.finish();
    }
  };

  page.init();
})();
