(function () {
  function isFormData(value) {
    return typeof FormData !== 'undefined' && value instanceof FormData;
  }

  function isBlob(value) {
    return typeof Blob !== 'undefined' && value instanceof Blob;
  }

  function normalizeOptions(methodOrOptions, body) {
    if (typeof methodOrOptions === 'string') {
      const opts = { method: methodOrOptions };
      if (body !== undefined) {
        if (isFormData(body) || isBlob(body) || typeof body === 'string') {
          opts.body = body;
        } else {
          opts.headers = { 'Content-Type': 'application/json' };
          opts.body = JSON.stringify(body);
        }
      }
      return opts;
    }

    return Object.assign({}, methodOrOptions || {});
  }

  function createAuthHttpClient(options) {
    const cfg = Object.assign({ authManager: null }, options || {});

    function getAuthManager() {
      if (!cfg.authManager) {
        throw new Error('Auth manager is required for auth-aware HTTP client');
      }
      return cfg.authManager;
    }

    async function fetchJson(url, methodOrOptions, body) {
      return await getAuthManager().fetchJson(url, normalizeOptions(methodOrOptions, body));
    }

    async function requestData(url, methodOrOptions, body) {
      const result = await fetchJson(url, methodOrOptions, body);
      if (result.unauthorized) {
        return { ok: false, unauthorized: true, error: 'Login required' };
      }

      const data = result.data;
      if (!data || typeof data !== 'object' || Array.isArray(data)) {
        return data;
      }

      return Object.assign(
        {
          ok: data.ok === undefined ? result.ok : data.ok,
          _status: result.status,
          _httpOk: result.ok,
        },
        data
      );
    }

    return {
      bindAuthManager: function bindAuthManager(authManager) {
        cfg.authManager = authManager;
        return this;
      },
      fetchJson: fetchJson,
      request: fetchJson,
      requestJson: fetchJson,
      requestData: requestData,
    };
  }

  window.createAuthHttpClient = createAuthHttpClient;
})();
