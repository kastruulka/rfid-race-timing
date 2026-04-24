(function () {
  const protocolUi = window.ProtocolUi;

  function getErrorMessage(result, fallback) {
    const data = result && result.data;
    if (data && typeof data === 'object' && data.error) return data.error;
    return fallback || 'Ошибка запроса';
  }

  function sanitizeFilenamePart(value, replacement) {
    return String(value || '')
      .split('')
      .map(function (char) {
        if (char.charCodeAt(0) < 32 || /[<>:"/\\|?*]/.test(char)) {
          return replacement;
        }
        return char;
      })
      .join('');
  }

  function createProtocolActions(deps) {
    function buildScopeFilenamePrefix() {
      const scope = deps.protocolScope.getScope();
      if (scope === 'all') return 'all-categories';

      const categoryNames = deps.protocolScope.getSelectedCategoryNames();
      if (scope === 'selected') {
        if (categoryNames.length === 1) return categoryNames[0];
        return 'selected-categories-' + categoryNames.length;
      }

      return categoryNames[0] || 'protocol';
    }

    function buildPdfFilename() {
      const prefix = sanitizeFilenamePart(buildScopeFilenamePrefix(), '_');
      const dateLabel = deps.els.date.value.trim() || new Date().toISOString().slice(0, 10);
      const safeDate = sanitizeFilenamePart(dateLabel, '-');
      return prefix + '-' + safeDate + '.pdf';
    }

    function buildSyncFilename() {
      const prefix = sanitizeFilenamePart(buildScopeFilenamePrefix(), '_');
      const dateLabel = deps.els.date.value.trim() || new Date().toISOString().slice(0, 10);
      const safeDate = sanitizeFilenamePart(dateLabel, '-');
      return prefix + '-' + safeDate + '.json';
    }

    async function generatePreview() {
      const body = deps.getProtocolRequestBody();
      if (!deps.protocolScope.ensureCategorySelection(body)) return;

      try {
        const result = await window.httpClient.fetchText('/api/protocol/preview', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });

        if (!result.ok) {
          deps.toast(getErrorMessage(result, 'Ошибка генерации предпросмотра'), true);
          return;
        }

        protocolUi.renderPreview(deps.els, result.data || '');
      } catch {
        deps.toast('Ошибка сети при загрузке предпросмотра', true);
      }
    }

    async function downloadPDF() {
      const body = deps.getProtocolRequestBody();
      if (!deps.protocolScope.ensureCategorySelection(body)) return;

      try {
        const result = await window.httpClient.fetchBlob('/api/protocol/pdf', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });

        if (!result.ok) {
          deps.toast(getErrorMessage(result, 'Ошибка генерации PDF'), true);
          return;
        }

        window.downloadBlob(result.data, buildPdfFilename());
      } catch {
        deps.toast('Ошибка сети при загрузке PDF', true);
      }
    }

    async function downloadSync() {
      const body = deps.getProtocolRequestBody();
      if (!deps.protocolScope.ensureCategorySelection(body)) return;

      try {
        const result = await window.httpClient.fetchBlob('/api/protocol/sync-export', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });

        if (!result.ok) {
          deps.toast(getErrorMessage(result, 'Ошибка экспорта JSON Sync'), true);
          return;
        }

        window.downloadBlob(result.data, buildSyncFilename());
      } catch {
        deps.toast('Ошибка сети при загрузке JSON Sync', true);
      }
    }

    return {
      downloadPDF: downloadPDF,
      downloadSync: downloadSync,
      generatePreview: generatePreview,
    };
  }

  window.createProtocolActions = createProtocolActions;
})();
