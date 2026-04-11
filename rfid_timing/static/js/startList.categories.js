(function () {
  const page = window.StartListPage || (window.StartListPage = {});

  function validateCategoryForm(body) {
    if (!body.name) return 'Введите название';
    if (
      !Number.isInteger(body.laps) ||
      body.laps < 1 ||
      body.laps > page.constants.MAX_CATEGORY_LAPS
    ) {
      return 'Количество кругов должно быть от 1 до ' + page.constants.MAX_CATEGORY_LAPS;
    }
    if (
      !Number.isFinite(body.distance_km) ||
      body.distance_km < 0 ||
      body.distance_km > page.constants.MAX_CATEGORY_DISTANCE
    ) {
      return 'Дистанция круга должна быть от 0 до ' + page.constants.MAX_CATEGORY_DISTANCE + ' км';
    }
    return null;
  }

  function createCategoryActions(catId, canEdit) {
    const actions = document.createElement('div');
    actions.className = 'cat-actions';

    const editBtn = document.createElement('button');
    editBtn.className = 'btn btn-sm';
    editBtn.type = 'button';
    editBtn.dataset.authRequired = 'true';
    editBtn.dataset.action = 'edit-category';
    editBtn.dataset.categoryId = String(catId);
    editBtn.title = 'Редакт.';
    editBtn.textContent = '✎';
    if (!canEdit) editBtn.disabled = true;

    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'btn btn-sm btn-danger';
    deleteBtn.type = 'button';
    deleteBtn.dataset.authRequired = 'true';
    deleteBtn.dataset.action = 'delete-category';
    deleteBtn.dataset.categoryId = String(catId);
    deleteBtn.title = 'Удалить';
    deleteBtn.textContent = '⨯';
    if (!canEdit) deleteBtn.disabled = true;

    actions.appendChild(editBtn);
    actions.appendChild(deleteBtn);
    return actions;
  }

  function createCategoryItem(category, canEdit) {
    const item = document.createElement('div');
    const isSelected = String(page.state.selectedCatId) === String(category.id);
    const warmupLabel =
      category.has_warmup_lap === false || category.has_warmup_lap === 0 ? ' · без разгонного' : '';

    item.className = 'cat-item' + (isSelected ? ' active' : '');
    item.dataset.categoryId = String(category.id);

    const textWrap = document.createElement('div');
    const name = document.createElement('div');
    name.className = 'cat-name';
    name.textContent = category.name || '';

    const meta = document.createElement('div');
    meta.className = 'cat-meta';
    meta.textContent =
      String(category.laps) + ' кр. · ' + String(category.distance_km || 0) + ' км' + warmupLabel;

    textWrap.appendChild(name);
    textWrap.appendChild(meta);

    const right = document.createElement('div');
    right.style.display = 'flex';
    right.style.alignItems = 'center';
    right.style.gap = '8px';

    const count = document.createElement('div');
    count.className = 'cat-count';
    count.textContent = String(category.rider_count || 0);

    right.appendChild(count);
    right.appendChild(createCategoryActions(category.id, canEdit));

    item.appendChild(textWrap);
    item.appendChild(right);
    return item;
  }

  function renderCategories() {
    const list = page.els.categoryList;
    const allItem = list.querySelector('[data-category-id=""]');
    const canEdit = !!(page.authManager && page.authManager.state.authenticated);
    let totalRiders = 0;

    list.innerHTML = '';
    list.appendChild(allItem);
    allItem.classList.toggle('active', !page.state.selectedCatId);

    page.state.categories.forEach(function (category) {
      list.appendChild(createCategoryItem(category, canEdit));
      totalRiders += category.rider_count || 0;
    });

    page.els.allCount.textContent = String(totalRiders);

    if (page.authManager) {
      page.authManager.syncProtectedControls();
    }
  }

  function selectCategory(categoryId) {
    page.state.selectedCatId = categoryId || '';
    renderCategories();
    page.loadRiders();
  }

  async function openCatModal(category) {
    const reason = category
      ? 'Для редактирования категории нужен пароль администратора'
      : 'Для добавления категории нужен пароль администратора';
    if (!(await page.ensureAuthenticated(reason))) return;

    page.els.categoryEditId.value = category ? String(category.id) : '';
    page.els.categoryName.value = category ? category.name || '' : '';
    page.els.categoryLaps.value = category ? String(category.laps) : '5';
    page.els.categoryDistance.value = category ? String(category.distance_km || 0) : '5';
    page.els.categoryWarmup.checked = category
      ? !(category.has_warmup_lap === false || category.has_warmup_lap === 0)
      : true;

    page.els.categoryModalTitle.textContent = category
      ? 'Редактировать категорию'
      : 'Новая категория';
    page.els.categoryModal.classList.add('open');
  }

  function closeCatModal() {
    page.els.categoryModal.classList.remove('open');
  }

  async function saveCat() {
    if (!(await page.ensureAuthenticated('Для сохранения категории нужен пароль администратора')))
      return;

    const categoryId = page.els.categoryEditId.value;
    const body = {
      name: page.els.categoryName.value.trim(),
      laps: parseInt(page.els.categoryLaps.value, 10) || 1,
      distance_km: parseFloat(page.els.categoryDistance.value) || 0,
      has_warmup_lap: page.els.categoryWarmup.checked,
    };
    const error = validateCategoryForm(body);
    if (error) {
      page.toast(error, true);
      return;
    }

    const result = categoryId
      ? await page.http.fetchJson('/api/categories/' + categoryId, 'PUT', body)
      : await page.http.fetchJson('/api/categories', 'POST', body);
    if (page.handleApiError(result)) return;

    page.toast(categoryId ? 'Категория обновлена' : 'Категория создана');
    closeCatModal();
    await page.loadInitialData();
  }

  async function editCat(categoryId) {
    if (
      !(await page.ensureAuthenticated('Для редактирования категории нужен пароль администратора'))
    )
      return;
    const category = page.state.categories.find(function (item) {
      return String(item.id) === String(categoryId);
    });
    if (category) {
      await openCatModal(category);
    }
  }

  async function deleteCat(categoryId) {
    if (!(await page.ensureAuthenticated('Для удаления категории нужен пароль администратора')))
      return;
    if (!window.confirm('Удалить категорию? Участники в ней не должны быть.')) return;

    const result = await page.http.fetchJson('/api/categories/' + categoryId, { method: 'DELETE' });
    if (page.handleApiError(result)) return;

    page.toast('Категория удалена');
    if (String(page.state.selectedCatId) === String(categoryId)) {
      page.state.selectedCatId = '';
    }
    await page.loadInitialData();
  }

  page.categories = {
    validateCategoryForm: validateCategoryForm,
    renderCategories: renderCategories,
    selectCategory: selectCategory,
    openCatModal: openCatModal,
    closeCatModal: closeCatModal,
    saveCat: saveCat,
    editCat: editCat,
    deleteCat: deleteCat,
  };
})();
