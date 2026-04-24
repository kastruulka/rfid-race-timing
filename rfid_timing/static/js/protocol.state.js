(function () {
  const STORAGE_KEY = 'rfid-protocol-form';

  function loadSavedState() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return {};
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === 'object' ? parsed : {};
    } catch {
      return {};
    }
  }

  function saveState(patch) {
    const current = loadSavedState();
    const next = Object.assign({}, current, patch);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      return;
    }
  }

  window.ProtocolState = {
    loadSavedState: loadSavedState,
    saveState: saveState,
  };
})();
