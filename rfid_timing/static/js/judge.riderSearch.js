(function () {
  const page = window.JudgePage || (window.JudgePage = {});

  page.createRiderDropdown = function createRiderDropdown(options) {
    const state = { index: -1, filtered: [] };

    function close() {
      options.listEl.classList.remove('open');
      state.index = -1;
    }

    function renderEmpty(text) {
      options.listEl.innerHTML = '';
      const empty = document.createElement('div');
      empty.style.padding = '8px 10px';
      empty.style.color = 'var(--text-dim)';
      empty.style.fontSize = '11px';
      empty.textContent = text;
      options.listEl.appendChild(empty);
    }

    function render() {
      state.filtered = Array.isArray(options.source()) ? options.source() : [];
      options.listEl.innerHTML = '';
      if (!state.filtered.length) {
        renderEmpty(
          typeof options.emptyText === 'function' ? options.emptyText() : options.emptyText
        );
        return;
      }
      state.filtered.forEach(function (rider, idx) {
        const item = document.createElement('div');
        const num = document.createElement('span');
        const name = document.createElement('span');
        item.className = 'rider-dropdown-item' + (idx === state.index ? ' active' : '');
        item.dataset.riderId = String(rider.id);
        num.className = 'rdi-num';
        num.textContent = '#' + rider.number;
        name.className = 'rdi-name';
        name.textContent = (rider.last_name || '') + ' ' + (rider.first_name || '');
        item.appendChild(num);
        item.appendChild(name);
        if (typeof options.renderMeta === 'function') {
          const meta = options.renderMeta(rider);
          if (meta) item.appendChild(meta);
        }
        options.listEl.appendChild(item);
      });
    }

    function highlight() {
      options.listEl.querySelectorAll('.rider-dropdown-item').forEach(function (el, idx) {
        el.classList.toggle('active', idx === state.index);
        if (idx === state.index) el.scrollIntoView({ block: 'nearest' });
      });
    }

    options.inputEl.addEventListener('input', function () {
      if (!String(options.inputEl.value || '').trim()) {
        close();
        if (typeof options.onClear === 'function') options.onClear();
        return;
      }
      state.index = -1;
      render();
      options.listEl.classList.add('open');
    });
    options.inputEl.addEventListener('focus', function () {
      options.inputEl.select();
      state.index = -1;
      render();
      options.listEl.classList.add('open');
    });
    options.inputEl.addEventListener('keydown', function (event) {
      const isOpen = options.listEl.classList.contains('open');
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        if (!isOpen) {
          render();
          options.listEl.classList.add('open');
        }
        state.index = Math.min(state.index + 1, state.filtered.length - 1);
        highlight();
      } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        state.index = Math.max(state.index - 1, 0);
        highlight();
      } else if (event.key === 'Enter') {
        event.preventDefault();
        if (state.index >= 0 && state.index < state.filtered.length)
          options.onSelect(state.filtered[state.index]);
        else if (state.filtered.length === 1) options.onSelect(state.filtered[0]);
      } else if (event.key === 'Escape') {
        close();
        options.inputEl.blur();
      }
    });
    options.listEl.addEventListener('click', function (event) {
      const item = event.target.closest('.rider-dropdown-item');
      if (!item) return;
      const rider = state.filtered.find(function (entry) {
        return String(entry.id) === item.dataset.riderId;
      });
      if (rider) options.onSelect(rider);
    });

    document.addEventListener('click', function (event) {
      if (options.inputEl.contains(event.target) || options.listEl.contains(event.target)) return;
      close();
    });

    return { close: close, render: render, state: state };
  };
})();
