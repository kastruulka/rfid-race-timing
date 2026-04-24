(function () {
  function formatCategoryLabel(category) {
    if (!category) return '';
    if (category.finish_mode === 'time' && category.time_limit_sec) {
      return category.name + ' (' + category.time_limit_sec + ' сек)';
    }
    return category.name + ' (' + category.laps + ' кр.)';
  }

  window.formatCategoryLabel = formatCategoryLabel;
})();
