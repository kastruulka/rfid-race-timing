(function () {
  const storageKey = 'rfid-theme';
  const root = document.documentElement;
  const media = window.matchMedia('(prefers-color-scheme: light)');

  function getStoredTheme() {
    try {
      const value = localStorage.getItem(storageKey);
      return value === 'light' || value === 'dark' ? value : null;
    } catch {
      return null;
    }
  }

  function getResolvedTheme() {
    return root.dataset.theme || (media.matches ? 'light' : 'dark');
  }

  function syncResolvedTheme() {
    root.dataset.themeResolved = getResolvedTheme();
    const toggle = document.getElementById('theme-toggle');
    if (!toggle) {
      return;
    }
    const isLight = getResolvedTheme() === 'light';
    toggle.setAttribute(
      'aria-label',
      isLight ? 'Переключить на тёмную тему' : 'Переключить на светлую тему'
    );
    toggle.setAttribute(
      'title',
      isLight ? 'Переключить на тёмную тему' : 'Переключить на светлую тему'
    );
    toggle.setAttribute('aria-pressed', String(isLight));
  }

  function applyTheme(theme) {
    root.dataset.theme = theme;
    try {
      localStorage.setItem(storageKey, theme);
    } catch {
      // Ignore storage write failures (private mode, restricted storage, etc.).
    }
    syncResolvedTheme();
  }

  function toggleTheme() {
    applyTheme(getResolvedTheme() === 'light' ? 'dark' : 'light');
  }

  document.addEventListener('DOMContentLoaded', () => {
    const toggle = document.getElementById('theme-toggle');
    syncResolvedTheme();
    if (toggle) {
      toggle.addEventListener('click', toggleTheme);
    }
  });

  if (typeof media.addEventListener === 'function') {
    media.addEventListener('change', () => {
      if (!getStoredTheme()) {
        syncResolvedTheme();
      }
    });
  } else if (typeof media.addListener === 'function') {
    media.addListener(() => {
      if (!getStoredTheme()) {
        syncResolvedTheme();
      }
    });
  }
})();
