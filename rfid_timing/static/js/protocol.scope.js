(function () {
  function createCategoryPickItem(category, checked, deps) {
    const label = document.createElement('label');
    label.className = 'cb-item category-pick-item';

    const input = document.createElement('input');
    input.type = 'checkbox';
    input.value = String(category.id);
    input.checked = checked;
    input.addEventListener('change', function () {
      deps.protocolState.saveState({ category_ids: deps.getSelectedCategoryIds() });
    });

    const text = document.createElement('span');
    text.className = 'category-pick-label';
    text.textContent = window.formatCategoryLabel(category);

    label.appendChild(input);
    label.appendChild(text);
    return label;
  }

  function populateMultiCategoryList(categories, selectedIds, deps) {
    if (!deps.els.categoryMulti) return;
    const selectedIdSet = new Set(selectedIds.map(String));
    deps.els.categoryMulti.innerHTML = '';

    categories.forEach(function (category) {
      const isChecked = selectedIdSet.has(String(category.id));
      deps.els.categoryMulti.appendChild(createCategoryPickItem(category, isChecked, deps));
    });
  }

  function createProtocolScope(deps) {
    function getScope() {
      return (deps.els.scope && deps.els.scope.value) || 'single';
    }

    function getSelectedCategoryId() {
      return parseInt(deps.els.category.value, 10) || null;
    }

    function getSelectedCategoryIds() {
      if (!deps.els.categoryMulti) return [];
      return Array.from(
        deps.els.categoryMulti.querySelectorAll('input[type="checkbox"]:checked')
      ).map(function (input) {
        return parseInt(input.value, 10);
      });
    }

    function getSelectedCategoryOption() {
      return deps.els.category.options[deps.els.category.selectedIndex] || null;
    }

    function getSelectedCategoryNames() {
      const scope = getScope();
      const categories = deps.getCategories();
      if (scope === 'all') {
        return categories.map(function (category) {
          return category.name;
        });
      }

      if (scope === 'selected') {
        const selectedIds = new Set(getSelectedCategoryIds());
        return categories
          .filter(function (category) {
            return selectedIds.has(Number(category.id));
          })
          .map(function (category) {
            return category.name;
          });
      }

      const option = getSelectedCategoryOption();
      if (!option || !option.value) return [];
      return [option.textContent.replace(/\s*\(.*/, '').trim()];
    }

    function ensureCategorySelection(body) {
      if (body.scope === 'all') return true;
      if (body.scope === 'selected') {
        if (body.category_ids.length > 0) return true;
        deps.toast('Выберите хотя бы одну категорию', true);
        return false;
      }
      if (body.category_id) return true;
      deps.toast('Выберите категорию', true);
      return false;
    }

    function updateScopeUi() {
      const scope = getScope();
      const singleVisible = scope === 'single';
      const multiVisible = scope === 'selected';

      if (deps.els.categorySingleWrap) {
        deps.els.categorySingleWrap.classList.toggle('hidden', !singleVisible);
      }
      if (deps.els.categoryMultiWrap) {
        deps.els.categoryMultiWrap.classList.toggle('hidden', !multiVisible);
      }
      deps.protocolState.saveState({ scope: scope });
    }

    function toggleAllCategoryChecks(checked) {
      if (!deps.els.categoryMulti) return;
      deps.els.categoryMulti.querySelectorAll('input[type="checkbox"]').forEach(function (input) {
        input.checked = checked;
      });
      deps.protocolState.saveState({ category_ids: getSelectedCategoryIds() });
    }

    async function loadCategories() {
      const result = await window.httpClient.fetchJson('/api/categories');
      const categories = Array.isArray(result.data) ? result.data : [];
      deps.setCategories(categories);
      const savedState = deps.protocolState.loadSavedState();

      const selectedSingleValue = deps.els.category.value || String(savedState.category_id || '');
      const selectedMultiValues = (
        getSelectedCategoryIds().length ? getSelectedCategoryIds() : savedState.category_ids || []
      ).map(String);

      deps.els.category.innerHTML = '';

      const placeholder = document.createElement('option');
      placeholder.value = '';
      placeholder.textContent = '-- Выберите категорию --';
      deps.els.category.appendChild(placeholder);

      categories.forEach(function (category) {
        const option = document.createElement('option');
        option.value = category.id;
        option.textContent = window.formatCategoryLabel(category);
        deps.els.category.appendChild(option);
      });

      if (
        selectedSingleValue &&
        categories.some(function (category) {
          return String(category.id) === String(selectedSingleValue);
        })
      ) {
        deps.els.category.value = selectedSingleValue;
      }

      populateMultiCategoryList(categories, selectedMultiValues, {
        els: deps.els,
        protocolState: deps.protocolState,
        getSelectedCategoryIds: getSelectedCategoryIds,
      });
      updateScopeUi();
    }

    return {
      ensureCategorySelection: ensureCategorySelection,
      getScope: getScope,
      getSelectedCategoryId: getSelectedCategoryId,
      getSelectedCategoryIds: getSelectedCategoryIds,
      getSelectedCategoryNames: getSelectedCategoryNames,
      loadCategories: loadCategories,
      toggleAllCategoryChecks: toggleAllCategoryChecks,
      updateScopeUi: updateScopeUi,
    };
  }

  window.createProtocolScope = createProtocolScope;
})();
