(function () {
  function showToast(message, isError) {
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

  window.showToast = showToast;
})();
