(function () {
  const page = window.JudgePage || (window.JudgePage = {});

  function buildEmptyMessage(text) {
    const wrapper = document.createElement('div');
    wrapper.style.padding = '40px 20px';
    wrapper.style.textAlign = 'center';
    wrapper.style.color = 'var(--text-dim)';
    wrapper.textContent = text;
    return wrapper;
  }

  function buildLogGroupTitle(text) {
    const title = document.createElement('div');
    title.style.padding = '5px 12px';
    title.style.fontSize = '9px';
    title.style.fontWeight = '700';
    title.style.textTransform = 'uppercase';
    title.style.letterSpacing = '0.08em';
    title.style.color = 'var(--accent)';
    title.style.background = 'var(--surface2)';
    title.style.borderBottom = '1px solid var(--border)';
    title.textContent = text;
    return title;
  }

  function buildLogItem(item, typeLabels) {
    const row = document.createElement('div');
    row.className = 'log-item';

    const badge = document.createElement('div');
    badge.className = 'li-badge ' + item.type;
    badge.textContent = typeLabels[item.type] || item.type;

    const info = document.createElement('div');
    info.className = 'li-info';

    const rider = document.createElement('div');
    rider.className = 'li-rider';
    rider.textContent = '#' + item.rider_number + ' ' + item.last_name;

    const detail = document.createElement('div');
    detail.className = 'li-detail';
    detail.textContent = item.reason || item.type;

    info.appendChild(rider);
    info.appendChild(detail);

    const time = document.createElement('div');
    time.className = 'li-time';
    time.textContent = new Date(item.created_at * 1000).toLocaleTimeString('ru-RU');

    const del = document.createElement('button');
    del.type = 'button';
    del.className = 'li-delete';
    del.dataset.action = 'delete-penalty';
    del.dataset.penaltyId = String(item.id);
    del.setAttribute('aria-label', 'Отменить решение');
    del.title = 'Отменить решение';
    del.textContent = '×';

    row.appendChild(badge);
    row.appendChild(info);
    row.appendChild(time);
    row.appendChild(del);

    return row;
  }

  async function deletePenalty(penaltyId) {
    if (!(await page.ensureJudgeAuth())) return;
    if (!window.confirm('Удалить это решение?')) return;
    const result = await page.api.deletePenalty(penaltyId);
    if (result.ok) {
      page.toast('Решение отменено');
      loadLog();
    } else {
      page.toast(result.error || 'Ошибка', true);
    }
  }

  async function loadLog() {
    try {
      const log = page.getResponseData(await page.api.getLog());
      page.els.logList.innerHTML = '';
      if (!Array.isArray(log) || !log.length) {
        page.els.logList.appendChild(buildEmptyMessage('Нет записей'));
        return;
      }

      const typeLabels = {
        TIME_PENALTY: 'Штраф',
        EXTRA_LAP: 'Доп. круг',
        WARNING: 'Предупр.',
        DSQ: 'DSQ',
        DNF: 'DNF',
      };
      const groups = {};
      const order = [];

      log.forEach(function (item) {
        const key = String(item.category_id || 0);
        if (!groups[key]) {
          groups[key] = { name: item.category_name || 'Без категории', items: [] };
          order.push(key);
        }
        groups[key].items.push(item);
      });

      order.forEach(function (key) {
        const group = groups[key];
        page.els.logList.appendChild(buildLogGroupTitle(group.name));
        group.items.forEach(function (item) {
          page.els.logList.appendChild(buildLogItem(item, typeLabels));
        });
      });
    } catch {
      // ignore polling errors
    }
  }

  function buildNoteItem(note) {
    const row = document.createElement('div');
    row.style.display = 'flex';
    row.style.gap = '8px';
    row.style.alignItems = 'center';
    row.style.padding = '8px 0';
    row.style.borderBottom = '1px solid var(--border)';
    row.style.fontSize = '12px';

    const textWrap = document.createElement('div');
    textWrap.style.flex = '1';
    textWrap.style.minWidth = '0';

    const rider = document.createElement('span');
    rider.style.color = 'var(--accent)';
    rider.style.fontWeight = '600';
    rider.textContent = note.rider_number
      ? '#' + note.rider_number + ' ' + (note.last_name || '') + ' - '
      : '';

    const text = document.createElement('span');
    text.style.color = 'var(--text)';
    text.textContent = note.text;

    textWrap.appendChild(rider);
    textWrap.appendChild(text);

    const time = document.createElement('span');
    time.style.color = 'var(--text-dim)';
    time.style.fontFamily = 'var(--mono)';
    time.style.fontSize = '10px';
    time.style.whiteSpace = 'nowrap';
    time.textContent = new Date(note.created_at * 1000).toLocaleTimeString('ru-RU');

    const del = document.createElement('button');
    del.type = 'button';
    del.className = 'note-del';
    del.dataset.action = 'delete-note';
    del.dataset.noteId = String(note.id);
    del.setAttribute('aria-label', 'Удалить заметку');
    del.title = 'Удалить заметку';
    del.textContent = '×';

    row.appendChild(textWrap);
    row.appendChild(time);
    row.appendChild(del);

    return row;
  }

  async function addNote() {
    if (!(await page.ensureJudgeAuth())) return;
    const text = page.els.noteText.value.trim();
    if (!text) {
      page.toast('Введите текст заметки', true);
      return;
    }
    const result = await page.api.addNote(text, page.state.selectedRiderId);
    if (result.ok) {
      page.toast('Заметка сохранена');
      page.els.noteText.value = '';
      loadNotes();
    } else {
      page.toast(result.error || 'Ошибка', true);
    }
  }

  async function deleteNote(noteId) {
    if (!(await page.ensureJudgeAuth())) return;
    const result = await page.api.deleteNote(noteId);
    if (result.ok) loadNotes();
  }

  async function loadNotes() {
    try {
      const notes = page.getResponseData(await page.api.getNotes());
      page.els.notesList.innerHTML = '';
      if (!Array.isArray(notes) || !notes.length) return;
      notes.forEach(function (note) {
        page.els.notesList.appendChild(buildNoteItem(note));
      });
    } catch {
      // ignore polling errors
    }
  }

  function bind() {
    page.els.logList.addEventListener('click', function (event) {
      const target = event.target.closest('[data-action="delete-penalty"]');
      if (!target) return;
      deletePenalty(parseInt(target.dataset.penaltyId, 10));
    });

    page.els.notesList.addEventListener('click', function (event) {
      const target = event.target.closest('[data-action="delete-note"]');
      if (!target) return;
      deleteNote(parseInt(target.dataset.noteId, 10));
    });

    page.els.noteText.addEventListener('keydown', function (event) {
      if (event.key !== 'Enter') return;
      event.preventDefault();
      addNote();
    });
  }

  page.logNotes = {
    addNote: addNote,
    bind: bind,
    deleteNote: deleteNote,
    deletePenalty: deletePenalty,
    loadLog: loadLog,
    loadNotes: loadNotes,
  };
})();
