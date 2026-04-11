(function () {
  const page = window.SettingsPage || (window.SettingsPage = {});

  page.DEFAULT_SETTINGS = {
    reader_port: 5084,
    tx_power: 30,
    rssi_window_sec: 0.5,
    min_lap_time_sec: 120,
    emulator_min_lap_sec: 15,
    antennas: [1, 2, 3, 4],
  };

  page.els = {
    readerIp: document.getElementById('s-reader-ip'),
    readerPort: document.getElementById('s-reader-port'),
    txPower: document.getElementById('s-tx-power'),
    antennas: [1, 2, 3, 4].map(function (index) {
      return document.getElementById('s-ant-' + index);
    }),
    rssiWindow: document.getElementById('s-rssi-window'),
    minLap: document.getElementById('s-min-lap'),
    useEmulator: document.getElementById('s-use-emulator'),
    emulatorMinLap: document.getElementById('s-emu-lap'),
    readerSettingsBlock: document.getElementById('reader-settings-block'),
    emulatorSettingsBlock: document.getElementById('emulator-settings-block'),
    filterSettingsBlock: document.getElementById('filter-settings-block'),
    checkConnectionButton: document.getElementById('btn-check-connection'),
    connectionBadge: document.getElementById('conn-status'),
    minLapLabel: document.getElementById('s-min-lap-label'),
    readerLabel: document.getElementById('mode-label-reader'),
    emulatorLabel: document.getElementById('mode-label-emulator'),
    readerModeBadge: document.getElementById('reader-mode-badge'),
    saveSettingsButton: document.getElementById('btn-save-settings'),
    backupDbButton: document.getElementById('btn-backup-db'),
    resetRaceButton: document.getElementById('btn-reset-race'),
    sysDb: document.getElementById('si-db'),
    sysLog: document.getElementById('si-log'),
    sysBackups: document.getElementById('si-bk'),
    sysRace: document.getElementById('si-race'),
    sysRiders: document.getElementById('si-riders'),
  };

  page.readSettingsForm = function readSettingsForm() {
    return {
      reader_ip: page.els.readerIp.value.trim(),
      reader_port: parseInt(page.els.readerPort.value, 10) || page.DEFAULT_SETTINGS.reader_port,
      tx_power: parseFloat(page.els.txPower.value) || page.DEFAULT_SETTINGS.tx_power,
      antennas: page.els.antennas
        .filter(function (checkbox) {
          return checkbox.checked;
        })
        .map(function (checkbox) {
          return parseInt(checkbox.value, 10);
        }),
      rssi_window_sec:
        parseFloat(page.els.rssiWindow.value) || page.DEFAULT_SETTINGS.rssi_window_sec,
      min_lap_time_sec: parseFloat(page.els.minLap.value) || page.DEFAULT_SETTINGS.min_lap_time_sec,
      use_emulator: !!page.els.useEmulator.checked,
      emulator_min_lap_sec:
        parseFloat(page.els.emulatorMinLap.value) || page.DEFAULT_SETTINGS.emulator_min_lap_sec,
    };
  };

  page.writeSettingsForm = function writeSettingsForm(data) {
    const settings = Object.assign({}, page.DEFAULT_SETTINGS, data || {});
    const activeAntennas =
      Array.isArray(settings.antennas) && settings.antennas.length
        ? settings.antennas
        : page.DEFAULT_SETTINGS.antennas;

    page.els.readerIp.value = settings.reader_ip || '';
    page.els.readerPort.value = settings.reader_port;
    page.els.txPower.value = settings.tx_power;
    page.els.rssiWindow.value = settings.rssi_window_sec;
    page.els.minLap.value = settings.min_lap_time_sec;
    page.els.useEmulator.checked = !!settings.use_emulator;
    page.els.emulatorMinLap.value = settings.emulator_min_lap_sec;

    page.els.antennas.forEach(function (checkbox, index) {
      checkbox.checked = activeAntennas.includes(index + 1);
    });
  };

  page.getSettingsPayload = function getSettingsPayload() {
    return page.readSettingsForm();
  };
})();
