(function () {
  const page = window.StartListPage || (window.StartListPage = {});

  function getCurrentEditingRiderId() {
    return parseInt(page.els.riderEditId.value, 10) || null;
  }

  function getEpcOwner(epc) {
    if (!epc) return null;
    return (
      page.state.riders.find(function (rider) {
        return String(rider.epc || '') === String(epc);
      }) || null
    );
  }

  function createScannerEmpty() {
    const empty = document.createElement('div');
    empty.style.padding = '12px';
    empty.style.border = '1px dashed var(--line)';
    empty.style.borderRadius = '12px';
    empty.style.color = 'var(--text-dim)';
    empty.style.fontSize = '12px';
    empty.textContent = 'Поднесите метку к антенне и дождитесь нового EPC.';
    return empty;
  }

  function createScannerItem(event, editingRiderId) {
    const owner = getEpcOwner(event.epc);
    const belongsToCurrent = owner && editingRiderId && owner.id === editingRiderId;
    const busy = owner && !belongsToCurrent;
    const card = document.createElement('div');
    const content = document.createElement('div');
    const right = document.createElement('div');
    const epc = document.createElement('div');
    const meta = document.createElement('div');
    const ownerInfo = document.createElement('div');
    const action = document.createElement('button');

    card.style.border = '1px solid var(--line)';
    card.style.borderRadius = '12px';
    card.style.padding = '10px 12px';
    card.style.display = 'grid';
    card.style.gridTemplateColumns = '1fr auto';
    card.style.gap = '10px';
    card.style.alignItems = 'center';

    epc.className = 'mono';
    epc.style.fontSize = '13px';
    epc.style.fontWeight = '700';
    epc.style.wordBreak = 'break-all';
    epc.textContent = event.epc || '';

    meta.style.fontSize = '11px';
    meta.style.color = 'var(--text-dim)';
    meta.style.marginTop = '4px';
    meta.textContent =
      'Время: ' +
      String(event.timestamp || '') +
      ' · Антенна: ' +
      String(event.antenna ?? '—') +
      ' · RSSI: ' +
      String(event.rssi ?? '—');

    ownerInfo.style.fontSize = '11px';
    ownerInfo.style.marginTop = '4px';
    ownerInfo.style.color = busy ? 'var(--red)' : 'var(--text-dim)';
    ownerInfo.textContent = owner
      ? 'Привязка: #' +
        owner.number +
        ' ' +
        String(owner.last_name || '') +
        (belongsToCurrent ? ' (этот участник)' : '')
      : 'Привязка: не привязана';

    action.className = 'btn btn-sm' + (busy ? '' : ' btn-accent');
    action.type = 'button';
    action.dataset.action = 'use-tag';
    action.dataset.epc = event.epc || '';
    action.textContent = busy ? 'Занято' : 'Использовать';
    if (busy) action.disabled = true;

    content.appendChild(epc);
    content.appendChild(meta);
    content.appendChild(ownerInfo);
    right.appendChild(action);
    card.appendChild(content);
    card.appendChild(right);

    return card;
  }

  function renderTagScanner(events) {
    page.els.tagScannerList.innerHTML = '';

    if (!Array.isArray(events) || !events.length) {
      page.els.tagScannerStatus.textContent = 'Последних считываний пока нет';
      page.els.tagScannerList.appendChild(createScannerEmpty());
      return;
    }

    page.els.tagScannerStatus.textContent = 'Последние считанные метки';
    const editingRiderId = getCurrentEditingRiderId();

    events.forEach(function (event) {
      page.els.tagScannerList.appendChild(createScannerItem(event, editingRiderId));
    });
  }

  async function pollTagScanner() {
    if (!page.els.tagScannerModal.classList.contains('open')) return;

    const events = (await page.fetchCollection('/api/events'))
      .filter(function (event) {
        return event && event.epc;
      })
      .slice(0, 12);
    const hash = events
      .map(function (event) {
        return [event.epc, event.timestamp, event.antenna].join('|');
      })
      .join('||');

    if (hash === page.state.tagScannerLastHash) return;

    page.state.tagScannerLastHash = hash;
    renderTagScanner(events);
  }

  async function openTagScanner() {
    if (!(await page.ensureAuthenticated('Для считывания EPC нужен пароль администратора'))) return;
    if (!page.els.riderModal.classList.contains('open')) return;

    page.state.tagScannerLastHash = '';
    page.els.tagScannerStatus.textContent = 'Ожидание считывания…';
    page.els.tagScannerList.innerHTML = '';
    page.els.tagScannerModal.classList.add('open');

    await pollTagScanner();

    if (!page.state.tagScannerTimer) {
      page.state.tagScannerTimer = window.setInterval(pollTagScanner, 1000);
    }
  }

  function closeTagScanner() {
    page.els.tagScannerModal.classList.remove('open');
    if (page.state.tagScannerTimer) {
      window.clearInterval(page.state.tagScannerTimer);
      page.state.tagScannerTimer = null;
    }
  }

  function useScannedTag(epc) {
    const owner = getEpcOwner(epc);
    const editingRiderId = getCurrentEditingRiderId();

    if (owner && owner.id !== editingRiderId) {
      page.toast('Эта метка уже привязана к #' + owner.number, true);
      return;
    }

    page.els.riderEpc.value = epc || '';
    closeTagScanner();
    page.toast('EPC подставлен в карточку участника');
  }

  page.tagScanner = {
    getCurrentEditingRiderId: getCurrentEditingRiderId,
    getEpcOwner: getEpcOwner,
    renderTagScanner: renderTagScanner,
    openTagScanner: openTagScanner,
    closeTagScanner: closeTagScanner,
    pollTagScanner: pollTagScanner,
    useScannedTag: useScannedTag,
  };
})();
