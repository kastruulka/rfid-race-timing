(function () {
  function renderPreview(els, html) {
    if (els.previewEmpty) {
      els.previewEmpty.remove();
      els.previewEmpty = null;
    }

    let paper = els.previewScroll.querySelector('.preview-paper');
    if (!paper) {
      paper = document.createElement('div');
      paper.className = 'preview-paper';
      els.previewScroll.appendChild(paper);
    }

    paper.innerHTML = html;
  }

  window.ProtocolUi = {
    renderPreview: renderPreview,
  };
})();
