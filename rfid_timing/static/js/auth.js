(function () {
  function getBaseHttpClient() {
    if (window.httpClient && typeof window.httpClient.fetchJson === 'function') {
      return window.httpClient;
    }

    return {
      fetchJson: async function (url, options) {
        const opts = Object.assign({ credentials: 'same-origin' }, options || {});
        const response = await fetch(url, opts);
        let data;

        try {
          data = await response.json();
        } catch {
          data = null;
        }

        return {
          ok: response.ok,
          status: response.status,
          data: data,
          unauthorized: response.status === 401,
        };
      },
    };
  }

  function createAuthMarkup() {
    return `
      <div class="auth-overlay hidden" id="auth-overlay">
        <div class="auth-dialog" role="dialog" aria-modal="true" aria-labelledby="auth-title">
          <button type="button" class="auth-close" id="auth-close" aria-label="Закрыть">×</button>
          <h2 class="auth-title" id="auth-title">Авторизация</h2>
          <div class="auth-subtitle" id="auth-subtitle">Введите пароль администратора</div>
          <input type="password" id="login-password" placeholder="Пароль" autocomplete="current-password">
          <div class="auth-error" id="login-error"></div>
          <div class="auth-actions">
            <button type="button" class="btn" id="auth-cancel">Закрыть</button>
            <button type="button" class="btn btn-accent" id="auth-submit">Войти</button>
          </div>
          <div class="auth-env-hint">
            Пароль задаётся через переменную окружения<br><code>RFID_ADMIN_PASSWORD</code>
          </div>
        </div>
      </div>
    `;
  }

  function getToastImpl(toast) {
    if (typeof toast === 'function') return toast;
    if (typeof window.showToast === 'function') return window.showToast;
    return function (message) {
      if (message) window.alert(message);
    };
  }

  function initAuthUi() {
    if (!document.getElementById('auth-overlay')) {
      document.body.insertAdjacentHTML('beforeend', createAuthMarkup());
    }

    return {
      overlay: document.getElementById('auth-overlay'),
      passwordInput: document.getElementById('login-password'),
      errorEl: document.getElementById('login-error'),
      subtitleEl: document.getElementById('auth-subtitle'),
      submitBtn: document.getElementById('auth-submit'),
      cancelBtn: document.getElementById('auth-cancel'),
      closeBtn: document.getElementById('auth-close'),
    };
  }

  function bindEvents(ui, handlers) {
    ui.overlay.addEventListener('click', function (event) {
      if (event.target === ui.overlay) handlers.closeLogin();
    });
    ui.closeBtn.addEventListener('click', handlers.closeLogin);
    ui.cancelBtn.addEventListener('click', handlers.closeLogin);
    ui.submitBtn.addEventListener('click', function () {
      handlers.login({ reason: ui.subtitleEl.textContent });
    });
    ui.passwordInput.addEventListener('keydown', function (event) {
      if (event.key === 'Enter') handlers.login({ reason: ui.subtitleEl.textContent });
      if (event.key === 'Escape') handlers.closeLogin();
    });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && handlers.isOpen()) handlers.closeLogin();
    });
  }

  function createAuthManager(options) {
    const cfg = Object.assign(
      {
        loginUrl: '/api/auth/login',
        logoutUrl: '/api/auth/logout',
        statusUrl: '/api/auth/status',
        loginButtonId: 'login-btn',
        logoutButtonId: 'logout-btn',
        authHintId: 'auth-hint',
        toast: null,
        onAuthChange: null,
      },
      options || {}
    );

    const toast = getToastImpl(cfg.toast);
    const ui = initAuthUi();
    const loginBtn = cfg.loginButtonId ? document.getElementById(cfg.loginButtonId) : null;
    const logoutBtn = cfg.logoutButtonId ? document.getElementById(cfg.logoutButtonId) : null;
    const authHint = cfg.authHintId ? document.getElementById(cfg.authHintId) : null;

    const state = {
      authenticated: false,
      csrfToken: null,
      resolved: false,
      isOpen: false,
    };

    function isMutatingMethod(method) {
      const upper = String(method || 'GET').toUpperCase();
      return upper === 'POST' || upper === 'PUT' || upper === 'PATCH' || upper === 'DELETE';
    }

    function setCsrfToken(nextToken) {
      state.csrfToken = nextToken || null;
    }

    function getCsrfHeaders(method) {
      if (!state.csrfToken || !isMutatingMethod(method)) return {};
      return { 'X-CSRF-Token': state.csrfToken };
    }

    function syncProtectedControls() {
      document.querySelectorAll('[data-auth-required]').forEach(function (el) {
        const authLocked = state.resolved && !state.authenticated;
        const stateLocked = el.dataset.stateDisabled === 'true';
        const finalDisabled = authLocked || stateLocked;
        const ariaValue = finalDisabled ? 'true' : 'false';

        if ('disabled' in el && el.disabled !== finalDisabled) {
          el.disabled = finalDisabled;
        }
        if (el.getAttribute('aria-disabled') !== ariaValue) {
          el.setAttribute('aria-disabled', ariaValue);
        }
        if (el.classList.contains('auth-disabled') !== authLocked) {
          el.classList.toggle('auth-disabled', authLocked);
        }
        if (el.classList.contains('is-disabled') !== finalDisabled) {
          el.classList.toggle('is-disabled', finalDisabled);
        }
      });
    }

    function clearError() {
      ui.errorEl.textContent = '';
    }

    function syncAuthState() {
      if (state.resolved) {
        if (logoutBtn) logoutBtn.classList.toggle('hidden', !state.authenticated);
        if (loginBtn) loginBtn.classList.toggle('hidden', state.authenticated);
        if (authHint) authHint.classList.toggle('hidden', state.authenticated);
      }
      syncProtectedControls();

      if (typeof cfg.onAuthChange === 'function') {
        cfg.onAuthChange(state.authenticated);
      }
    }

    function openLogin(reason) {
      ui.subtitleEl.textContent = reason || 'Введите пароль администратора';
      clearError();
      ui.overlay.classList.remove('hidden');
      state.isOpen = true;
      window.setTimeout(function () {
        ui.passwordInput.focus();
        ui.passwordInput.select();
      }, 0);
    }

    function closeLogin() {
      ui.overlay.classList.add('hidden');
      state.isOpen = false;
      clearError();
      ui.passwordInput.value = '';
    }

    async function handleUnauthorized(reason) {
      state.authenticated = false;
      state.resolved = true;
      setCsrfToken(null);
      syncAuthState();
      openLogin(reason || 'Сессия истекла. Войдите заново');
      toast('Требуется авторизация', true);
    }

    async function checkAuth() {
      try {
        const resp = await fetch(cfg.statusUrl, { credentials: 'same-origin' });
        const data = await resp.json();
        state.authenticated = !!(data && data.authenticated);
        setCsrfToken(data && data.csrf_token);
      } catch {
        state.authenticated = false;
        setCsrfToken(null);
      }
      state.resolved = true;

      syncAuthState();
      return state.authenticated;
    }

    async function login(options) {
      const opts = typeof options === 'string' ? { reason: options } : options || {};
      const password =
        typeof opts.password === 'string' ? opts.password.trim() : ui.passwordInput.value.trim();
      const reason = opts.reason || 'Введите пароль администратора';

      clearError();

      if (!password) {
        openLogin(reason);
        if (!opts.silent) {
          ui.errorEl.textContent = 'Введите пароль';
          ui.passwordInput.focus();
        }
        return false;
      }

      ui.submitBtn.disabled = true;
      try {
        const resp = await fetch(cfg.loginUrl, {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ password: password }),
        });
        const data = await resp.json();

        if (!resp.ok || !data.ok) {
          openLogin(reason);
          ui.errorEl.textContent = data.error || 'Ошибка входа';
          ui.passwordInput.focus();
          ui.passwordInput.select();
          return false;
        }

        setCsrfToken(data && data.csrf_token);
        state.authenticated = true;
        state.resolved = true;
        closeLogin();
        syncAuthState();
        toast('Авторизация успешна');
        return true;
      } catch {
        openLogin(reason);
        ui.errorEl.textContent = 'Ошибка сети';
        return false;
      } finally {
        ui.submitBtn.disabled = false;
      }
    }

    async function logout() {
      try {
        await fetch(cfg.logoutUrl, {
          method: 'POST',
          credentials: 'same-origin',
          headers: getCsrfHeaders('POST'),
        });
      } catch {
        // ignore
      }

      state.authenticated = false;
      state.resolved = true;
      setCsrfToken(null);
      closeLogin();
      syncAuthState();
      toast('Вы вышли');
    }

    async function fetchJson(url, options) {
      const http = getBaseHttpClient();
      const opts = Object.assign({ credentials: 'same-origin' }, options || {});
      const method = opts.method || 'GET';
      const unauthorizedMessage = opts.unauthorizedMessage;
      delete opts.unauthorizedMessage;
      opts.headers = Object.assign({}, getCsrfHeaders(method), opts.headers || {});

      const result = await http.fetchJson(url, opts);
      const data = result.data;
      const unauthorized = result.unauthorized;

      if (unauthorized) {
        await handleUnauthorized((data && data.error) || unauthorizedMessage);
      } else if (result.status === 403 && data && data.error === 'CSRF token missing or invalid') {
        setCsrfToken(null);
        await checkAuth();
      }

      return {
        ok: result.ok && !unauthorized,
        status: result.status,
        data: data,
        unauthorized: unauthorized,
      };
    }

    bindEvents(ui, {
      closeLogin: closeLogin,
      login: login,
      isOpen: function () {
        return state.isOpen;
      },
    });

    if (loginBtn) {
      loginBtn.addEventListener('click', function () {
        login({ reason: 'Введите пароль администратора', silent: true });
      });
    }
    if (logoutBtn) {
      logoutBtn.addEventListener('click', logout);
    }

    syncAuthState();

    return {
      state: state,
      checkAuth: checkAuth,
      login: login,
      logout: logout,
      fetchJson: fetchJson,
      syncProtectedControls: syncProtectedControls,
    };
  }

  window.createAuthManager = createAuthManager;
})();
