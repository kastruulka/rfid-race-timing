(function () {
  function createAuthMarkup() {
    return (
      '<div class="auth-overlay hidden" id="auth-overlay">' +
        '<div class="auth-dialog" role="dialog" aria-modal="true" aria-labelledby="auth-title">' +
          '<button type="button" class="auth-close" id="auth-close" aria-label="Закрыть">×</button>' +
          '<h2 class="auth-title" id="auth-title">Авторизация</h2>' +
          '<div class="auth-subtitle" id="auth-subtitle">Введите пароль администратора</div>' +
          '<input type="password" id="login-password" placeholder="Пароль" autocomplete="current-password">' +
          '<div class="auth-error" id="login-error"></div>' +
          '<div class="auth-actions">' +
            '<button type="button" class="btn" id="auth-cancel">Закрыть</button>' +
            '<button type="button" class="btn btn-accent" id="auth-submit">Войти</button>' +
          '</div>' +
          '<div class="auth-env-hint">' +
            'Пароль задаётся через переменную окружения<br><code>RFID_ADMIN_PASSWORD</code>' +
          '</div>' +
        '</div>' +
      '</div>'
    );
  }

  function defaultToast(message, isError) {
    const toastEl = document.getElementById('toast');
    if (!toastEl) {
      if (message) window.alert(message);
      return;
    }
    toastEl.textContent = message;
    toastEl.className = 'toast show' + (isError ? ' error' : '');
    clearTimeout(toastEl._timer);
    toastEl._timer = setTimeout(function () {
      toastEl.className = 'toast';
    }, 2500);
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
        toast: defaultToast,
        onAuthChange: null,
      },
      options || {}
    );

    if (!document.getElementById('auth-overlay')) {
      document.body.insertAdjacentHTML('beforeend', createAuthMarkup());
    }

    const overlay = document.getElementById('auth-overlay');
    const passwordInput = document.getElementById('login-password');
    const errorEl = document.getElementById('login-error');
    const subtitleEl = document.getElementById('auth-subtitle');
    const submitBtn = document.getElementById('auth-submit');
    const cancelBtn = document.getElementById('auth-cancel');
    const closeBtn = document.getElementById('auth-close');
    const loginBtn = cfg.loginButtonId ? document.getElementById(cfg.loginButtonId) : null;
    const logoutBtn = cfg.logoutButtonId ? document.getElementById(cfg.logoutButtonId) : null;
    const authHint = cfg.authHintId ? document.getElementById(cfg.authHintId) : null;

    let authenticated = false;
    let csrfToken = null;
    let isOpen = false;

    function isMutatingMethod(method) {
      const upper = String(method || 'GET').toUpperCase();
      return upper === 'POST' || upper === 'PUT' || upper === 'PATCH' || upper === 'DELETE';
    }

    function setCsrfToken(nextToken) {
      csrfToken = nextToken || null;
    }

    function getCsrfHeaders(method) {
      if (!csrfToken || !isMutatingMethod(method)) return {};
      return { 'X-CSRF-Token': csrfToken };
    }

    function syncProtectedControls() {
      document.querySelectorAll('[data-auth-required]').forEach(function (el) {
        const shouldLock = !authenticated;
        const stateLocked = el.dataset.stateDisabled === 'true';
        const finalDisabled = shouldLock || stateLocked;
        if ('disabled' in el && el.disabled !== finalDisabled) {
          el.disabled = finalDisabled;
        }
        if (el.classList.contains('auth-disabled') !== shouldLock) {
          el.classList.toggle('auth-disabled', shouldLock);
        }
      });
    }

    function syncAuthState() {
      if (logoutBtn) logoutBtn.classList.toggle('hidden', !authenticated);
      if (loginBtn) loginBtn.classList.toggle('hidden', authenticated);
      if (authHint) authHint.classList.toggle('hidden', authenticated);
      syncProtectedControls();
      if (typeof cfg.onAuthChange === 'function') {
        cfg.onAuthChange(authenticated);
      }
    }

    function clearError() {
      errorEl.textContent = '';
    }

    function openLogin(reason) {
      subtitleEl.textContent = reason || 'Введите пароль администратора';
      clearError();
      overlay.classList.remove('hidden');
      isOpen = true;
      window.setTimeout(function () {
        passwordInput.focus();
        passwordInput.select();
      }, 0);
    }

    function closeLogin() {
      overlay.classList.add('hidden');
      isOpen = false;
      clearError();
      passwordInput.value = '';
    }

    async function setAuthenticated(nextValue) {
      authenticated = !!nextValue;
      if (authenticated) closeLogin();
      syncAuthState();
    }

    async function checkAuth() {
      try {
        const resp = await fetch(cfg.statusUrl, { credentials: 'same-origin' });
        const data = await resp.json();
        authenticated = !!data.authenticated;
        setCsrfToken(data && data.csrf_token);
      } catch (err) {
        authenticated = false;
        setCsrfToken(null);
      }
      syncAuthState();
      return authenticated;
    }

    async function login() {
      const password = passwordInput.value.trim();
      clearError();

      if (!password) {
        errorEl.textContent = 'Введите пароль';
        passwordInput.focus();
        return false;
      }

      submitBtn.disabled = true;
      try {
        const resp = await fetch(cfg.loginUrl, {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ password: password }),
        });
        const data = await resp.json();

        if (!resp.ok || !data.ok) {
          errorEl.textContent = data.error || 'Ошибка входа';
          passwordInput.focus();
          passwordInput.select();
          return false;
        }

        setCsrfToken(data && data.csrf_token);
        await setAuthenticated(true);
        cfg.toast('Авторизация успешна');
        return true;
      } catch (err) {
        errorEl.textContent = 'Ошибка сети';
        return false;
      } finally {
        submitBtn.disabled = false;
      }
    }

    async function logout() {
      try {
        await fetch(cfg.logoutUrl, {
          method: 'POST',
          credentials: 'same-origin',
          headers: getCsrfHeaders('POST'),
        });
      } catch (err) {
        // ignore network problems and still drop local state
      }
      authenticated = false;
      setCsrfToken(null);
      syncAuthState();
      cfg.toast('Вы вышли');
    }

    async function requireAuth(reason) {
      if (authenticated) return true;
      openLogin(reason || 'Для этого действия нужен пароль администратора');
      return false;
    }

    async function handleUnauthorized(reason) {
      authenticated = false;
      setCsrfToken(null);
      syncAuthState();
      openLogin(reason || 'Сессия истекла. Войдите заново');
      cfg.toast('Требуется авторизация', true);
      return null;
    }

    async function fetchJson(url, options) {
      const opts = Object.assign({ credentials: 'same-origin' }, options || {});
      const method = opts.method || 'GET';
      opts.headers = Object.assign({}, getCsrfHeaders(method), opts.headers || {});

      const resp = await fetch(url, opts);
      let data = null;
      try {
        data = await resp.json();
      } catch (err) {
        data = null;
      }

      if (resp.status === 401) {
        await handleUnauthorized((data && data.error) || 'Сессия истекла. Войдите заново');
        return { ok: false, unauthorized: true, status: resp.status, data: data };
      }

      if (resp.status === 403 && data && data.error === 'CSRF token missing or invalid') {
        setCsrfToken(null);
        await checkAuth();
      }

      return { ok: resp.ok, status: resp.status, data: data };
    }

    overlay.addEventListener('click', function (event) {
      if (event.target === overlay) closeLogin();
    });
    closeBtn.addEventListener('click', closeLogin);
    cancelBtn.addEventListener('click', closeLogin);
    submitBtn.addEventListener('click', login);
    passwordInput.addEventListener('keydown', function (event) {
      if (event.key === 'Enter') login();
      if (event.key === 'Escape') closeLogin();
    });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && isOpen) closeLogin();
    });
    if (loginBtn) {
      loginBtn.addEventListener('click', function () {
        openLogin('Введите пароль администратора');
      });
    }
    if (logoutBtn) {
      logoutBtn.addEventListener('click', logout);
    }

    syncAuthState();

    return {
      checkAuth: checkAuth,
      openLogin: openLogin,
      closeLogin: closeLogin,
      login: login,
      logout: logout,
      requireAuth: requireAuth,
      handleUnauthorized: handleUnauthorized,
      fetchJson: fetchJson,
      getCsrfHeaders: getCsrfHeaders,
      isAuthenticated: function () { return authenticated; },
      syncProtectedControls: syncProtectedControls,
    };
  }

  window.createAuthManager = createAuthManager;
})();
