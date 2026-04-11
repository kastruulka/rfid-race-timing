(function () {
  const page = window.SettingsPage || (window.SettingsPage = {});

  page.setStatusBadge = function setStatusBadge(el, className, text, title) {
    if (!el) return;
    el.className = 'status-badge ' + className;
    el.textContent = text;
    if (title !== undefined) el.title = title;
  };

  page.updateModeVisibility = function updateModeVisibility() {
    const useEmulator = !!page.els.useEmulator.checked;
    const visibilityMap = [
      { element: page.els.readerSettingsBlock, hidden: useEmulator },
      { element: page.els.filterSettingsBlock, hidden: useEmulator },
      { element: page.els.emulatorSettingsBlock, hidden: !useEmulator },
      { element: page.els.checkConnectionButton, hidden: useEmulator },
      { element: page.els.connectionBadge, hidden: useEmulator },
    ];

    visibilityMap.forEach(function (entry) {
      if (!entry.element) return;
      entry.element.classList.toggle('hidden', !!entry.hidden);
    });

    if (page.els.readerLabel) page.els.readerLabel.classList.toggle('active', !useEmulator);
    if (page.els.emulatorLabel) page.els.emulatorLabel.classList.toggle('active', useEmulator);
    if (page.els.minLapLabel) {
      page.els.minLapLabel.textContent = useEmulator
        ? 'Антидребезг эмулятора (сек)'
        : 'Антидребезг ридера (сек)';
    }

    page.setStatusBadge(
      page.els.readerModeBadge,
      useEmulator ? 'wait' : 'ok',
      useEmulator ? 'Эмулятор' : 'Считыватель'
    );
  };

  page.loadReaderStatus = async function loadReaderStatus() {
    try {
      const result = await page.http.fetchJson('/api/settings/reader-status');
      const status = result.data;
      if (!status) return;

      if (!status.running) {
        page.setStatusBadge(page.els.readerModeBadge, 'err', 'Остановлен');
      } else if (status.mode === 'emulator') {
        page.setStatusBadge(page.els.readerModeBadge, 'wait', 'Эмулятор');
      } else {
        page.setStatusBadge(page.els.readerModeBadge, 'ok', 'Ридер ' + (status.reader_ip || ''));
      }
    } catch {
      // ignore
    }
  };
})();
