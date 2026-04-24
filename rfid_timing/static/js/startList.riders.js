(function () {
  const page = window.StartListPage || (window.StartListPage = {});

  function validateRiderForm(body) {
    if (
      !Number.isInteger(body.number) ||
      body.number < 1 ||
      body.number > page.constants.MAX_NUMBER
    ) {
      return 'Стартовый номер должен быть от 1 до ' + page.constants.MAX_NUMBER;
    }
    if (!body.last_name) return 'Номер и фамилия обязательны';
    if (body.birth_year !== null) {
      if (
        !Number.isInteger(body.birth_year) ||
        body.birth_year < page.constants.MIN_BIRTH_YEAR ||
        body.birth_year > page.constants.CURRENT_YEAR
      ) {
        return (
          'Год рождения должен быть в диапазоне ' +
          page.constants.MIN_BIRTH_YEAR +
          '-' +
          page.constants.CURRENT_YEAR
        );
      }
    }
    return null;
  }

  function getFilteredRiders() {
    const query = page.els.searchInput.value.trim().toLowerCase();
    return page.state.riders.filter(function (rider) {
      if (!query) return true;
      return (
        String(rider.number).includes(query) ||
        String(rider.last_name || '')
          .toLowerCase()
          .includes(query) ||
        String(rider.first_name || '')
          .toLowerCase()
          .includes(query) ||
        String(rider.club || '')
          .toLowerCase()
          .includes(query) ||
        String(rider.city || '')
          .toLowerCase()
          .includes(query) ||
        String(rider.epc || '')
          .toLowerCase()
          .includes(query)
      );
    });
  }

  function createActionButton(label, action, riderId, extraClass, title, disabled) {
    const button = document.createElement('button');
    button.className = 'btn btn-sm' + (extraClass ? ' ' + extraClass : '');
    button.type = 'button';
    button.dataset.authRequired = 'true';
    button.dataset.action = action;
    button.dataset.riderId = String(riderId);
    button.title = title;
    button.textContent = label;
    if (disabled) button.disabled = true;
    return button;
  }

  function createCell(text, className) {
    const cell = document.createElement('td');
    if (className) cell.className = className;
    cell.textContent = text;
    return cell;
  }

  function renderRiders() {
    const tbody = page.els.ridersBody;
    const filtered = getFilteredRiders();
    const canEdit = !!(page.authManager && page.authManager.state.authenticated);

    tbody.innerHTML = '';

    filtered.forEach(function (rider) {
      const row = document.createElement('tr');
      const actionsCol = document.createElement('td');
      const actionsWrap = document.createElement('div');
      const epcCell = document.createElement('td');
      const hasEpc = !!(rider.epc && rider.epc.length);

      row.appendChild(createCell(String(rider.number), 'num-col'));

      const lastName = createCell(rider.last_name || '');
      lastName.style.fontWeight = '600';
      row.appendChild(lastName);

      row.appendChild(createCell(rider.first_name || ''));
      row.appendChild(createCell(rider.birth_year || '—', 'c mono'));
      row.appendChild(createCell(rider.city || '—'));
      row.appendChild(createCell(rider.club || '—'));
      row.appendChild(createCell(rider.category_name || '—'));

      epcCell.className = 'epc-col' + (hasEpc ? ' bound' : '');
      epcCell.title = rider.epc || '';
      epcCell.textContent = hasEpc ? rider.epc : '—';
      row.appendChild(epcCell);

      actionsWrap.className = 'actions-col';
      actionsWrap.appendChild(
        createActionButton('✎', 'edit-rider', rider.id, '', 'Редакт.', !canEdit)
      );
      actionsWrap.appendChild(
        createActionButton('⨯', 'delete-rider', rider.id, 'btn-danger', 'Удалить', !canEdit)
      );
      actionsCol.appendChild(actionsWrap);
      row.appendChild(actionsCol);

      tbody.appendChild(row);
    });

    page.els.emptyState.style.display = filtered.length ? 'none' : 'flex';

    if (page.authManager) {
      page.authManager.syncProtectedControls();
    }
  }

  function updateStats() {
    const total = page.state.riders.length;
    const withEpc = page.state.riders.filter(function (rider) {
      return rider.epc && rider.epc.length > 0;
    }).length;

    page.els.statTotal.textContent = String(total);
    page.els.statEpc.textContent = String(withEpc);
    page.els.statNoEpc.textContent = String(total - withEpc);
  }

  function applySearch() {
    renderRiders();
  }

  function fillCategoryOptions(selectedCategoryId, preferSelectedCategory) {
    page.els.riderCategory.innerHTML = '';

    const emptyOption = document.createElement('option');
    emptyOption.value = '';
    emptyOption.textContent = '— без категории —';
    page.els.riderCategory.appendChild(emptyOption);

    page.state.categories.forEach(function (category) {
      const option = document.createElement('option');
      option.value = String(category.id);
      option.textContent = category.name || '';
      option.selected = String(selectedCategoryId) === String(category.id);
      page.els.riderCategory.appendChild(option);
    });

    if (!selectedCategoryId && preferSelectedCategory && page.state.selectedCatId) {
      page.els.riderCategory.value = String(page.state.selectedCatId);
    }
  }

  async function openRiderModal(rider) {
    const reason = rider
      ? 'Для редактирования участника нужен пароль администратора'
      : 'Для добавления участника нужен пароль администратора';
    if (!(await page.ensureAuthenticated(reason))) return;

    page.els.riderEditId.value = rider ? String(rider.id) : '';
    page.els.riderNumber.value = rider ? String(rider.number) : '';
    page.els.riderLastName.value = rider ? rider.last_name || '' : '';
    page.els.riderFirstName.value = rider ? rider.first_name || '' : '';
    page.els.riderBirthYear.value = rider ? String(rider.birth_year || '') : '';
    page.els.riderCity.value = rider ? rider.city || '' : '';
    page.els.riderClub.value = rider ? rider.club || '' : '';
    page.els.riderEpc.value = rider ? rider.epc || '' : '';
    page.els.riderModalTitle.textContent = rider ? 'Редактировать участника' : 'Новый участник';

    fillCategoryOptions(rider ? rider.category_id : null, !rider);
    page.els.riderModal.classList.add('open');
  }

  function closeRiderModal() {
    page.tagScanner.closeTagScanner();
    page.els.riderModal.classList.remove('open');
  }

  async function saveRider() {
    if (!(await page.ensureAuthenticated('Для сохранения участника нужен пароль администратора')))
      return;

    const riderId = page.els.riderEditId.value;
    const body = {
      number: parseInt(page.els.riderNumber.value, 10),
      last_name: page.els.riderLastName.value.trim(),
      first_name: page.els.riderFirstName.value.trim(),
      birth_year: parseInt(page.els.riderBirthYear.value, 10) || null,
      city: page.els.riderCity.value.trim(),
      club: page.els.riderClub.value.trim(),
      category_id: parseInt(page.els.riderCategory.value, 10) || null,
      epc: page.els.riderEpc.value.trim() || null,
    };
    const error = validateRiderForm(body);
    if (error) {
      page.toast(error, true);
      return;
    }

    const result = riderId
      ? await page.http.fetchJson('/api/riders/' + riderId, 'PUT', body)
      : await page.http.fetchJson('/api/riders', 'POST', body);
    if (page.handleApiError(result)) return;

    page.toast(riderId ? 'Участник обновлён' : 'Участник добавлен');
    closeRiderModal();
    await page.loadInitialData();
  }

  async function editRider(riderId) {
    if (
      !(await page.ensureAuthenticated('Для редактирования участника нужен пароль администратора'))
    )
      return;
    const rider = page.state.riders.find(function (item) {
      return String(item.id) === String(riderId);
    });
    if (rider) {
      await openRiderModal(rider);
    }
  }

  async function deleteRider(riderId) {
    if (!(await page.ensureAuthenticated('Для удаления участника нужен пароль администратора')))
      return;

    const rider = page.state.riders.find(function (item) {
      return String(item.id) === String(riderId);
    });
    const label = rider ? '#' + rider.number + ' ' + rider.last_name : '#' + riderId;
    if (!window.confirm('Удалить участника ' + label + '?')) return;

    const result = await page.http.fetchJson('/api/riders/' + riderId, { method: 'DELETE' });
    if (page.handleApiError(result)) return;

    page.toast('Участник удалён');
    await page.loadInitialData();
  }

  page.riders = {
    validateRiderForm: validateRiderForm,
    renderRiders: renderRiders,
    openRiderModal: openRiderModal,
    closeRiderModal: closeRiderModal,
    saveRider: saveRider,
    editRider: editRider,
    deleteRider: deleteRider,
    updateStats: updateStats,
    applySearch: applySearch,
    getFilteredRiders: getFilteredRiders,
  };
})();
