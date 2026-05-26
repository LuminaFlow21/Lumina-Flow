(() => {
  const noop = () => {
    console.warn('edit_quotation_modal: action called before initialization');
  };

  const previousHandlers = {
    open: typeof window.openEditModal === 'function' ? window.openEditModal : undefined,
    close: typeof window.closeEditModal === 'function' ? window.closeEditModal : undefined,
    image: typeof window.downloadImage === 'function' ? window.downloadImage : undefined,
    pdf: typeof window.downloadPDF === 'function' ? window.downloadPDF : undefined,
    share: typeof window.shareQuotation === 'function' ? window.shareQuotation : undefined,
  };

  let handlersAssigned = false;

  try {
    const modal = document.getElementById('editModal');
    if (!modal) {
      return;
    }

    const root = modal.querySelector('[data-quotation-root]');
    if (!root) {
      return;
    }

    modal.setAttribute('tabindex', '-1');

    const type = (root.dataset.quotationType || 'quick').toLowerCase();
    const currencySymbol = root.dataset.currencySymbol || 'R$';
    const currencyCode = (root.dataset.currencyCode || 'BRL').toUpperCase();
    const saveEndpoint = root.dataset.saveEndpoint;
    const locale = getLocaleForCurrency(currencyCode);
    const numberFormatter = new Intl.NumberFormat(locale, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
    const quantityFormatter = new Intl.NumberFormat(locale, {
      maximumFractionDigits: 2,
    });

    modal.classList.add(`edit-template-modal--${type}`);

    let baseData = {};
    const dataScript = modal.querySelector('#quotationEditorData');
    if (dataScript) {
      try {
        baseData = JSON.parse(dataScript.textContent || '{}') || {};
      } catch (error) {
        console.warn('edit_quotation_modal: unable to parse initial data', error);
      }
    }

    const state = {
      client_name: baseData.client_name || '',
      phone: baseData.phone || '',
      address: baseData.address || '',
      service_description: baseData.service_description || '',
      value: toNumber(baseData.value ?? root.dataset.totalValue),
      expiry_date: normalizeDate(baseData.expiry_date) || '',
      notes: baseData.notes || '',
      discount: toNumber(baseData.discount),
      items: Array.isArray(baseData.items) ? baseData.items.map(normalizeItem) : [],
    };

    if (type !== 'detailed') {
      state.address = '';
      state.discount = 0;
      state.items = [];
    }

    const fieldElements = Array.from(
      modal.querySelectorAll('[contenteditable][data-field]')
    ).filter(isFieldRelevant);
    const itemsRoot = type === 'detailed' ? modal.querySelector('[data-items-root]') : null;
    const addItemButton = type === 'detailed' ? modal.querySelector('[data-action="add-item"]') : null;
    const closeButtons = modal.querySelectorAll('[data-modal-close]');
    const saveButton = modal.querySelector('[data-action="save"]');
    const cancelButton = modal.querySelector('[data-action="cancel"]');
    const valueField = modal.querySelector('[data-field="value"]');
    const discountField = modal.querySelector('[data-field="discount"]');
    const expiryField = modal.querySelector('[data-field="expiry_date"]');
    const summaryClientEl = modal.querySelector('[data-summary="client"]');
    const summaryValueEl = modal.querySelector('[data-summary="value"]');
    const summaryExpiryEl = modal.querySelector('[data-summary="expiry"]');
    const overviewValueEl = modal.querySelector('[data-overview="value"]');
    const overviewExpiryEl = modal.querySelector('[data-overview="expiry"]');
    const overviewDiscountEl = modal.querySelector('[data-overview="discount"]');
    const qaActions = document.querySelector('.qa-actions');
    const tipsToggle = modal.querySelector('[data-tips-toggle]');
    const tipsPanel = modal.querySelector('[data-tips-panel]');
    const tipsClose = modal.querySelector('[data-tips-close]');
    const confirmRoot = modal.querySelector('[data-confirm-root]');
    const confirmMessageEl = confirmRoot?.querySelector('[data-confirm-message]');
    const confirmPrimaryBtn = confirmRoot?.querySelector('[data-confirm-action="primary"]');
    const confirmSecondaryBtn = confirmRoot?.querySelector('[data-confirm-action="secondary"]');
    const confirmDismissBtn = confirmRoot?.querySelector('[data-confirm-dismiss]');
    const confirmCard = confirmRoot?.querySelector('.edit-template-modal__confirm-card');
    let confirmState = null;
    let previousActiveElement = null;

    window.openEditModal = openModal;
    window.closeEditModal = closeModal;
    window.downloadImage = downloadImage;
    window.downloadPDF = downloadPDF;
    window.shareQuotation = shareQuotation;
    handlersAssigned = true;

    const initialItemsTotal = computeItemsTotal(state.items);
    let manualValueOverride = type === 'detailed' ? false : true;
    if (type === 'detailed') {
      syncDetailedTotals({ itemsTotal: initialItemsTotal });
    }

    fieldElements.forEach(setupField);
    if (type === 'detailed' && itemsRoot) {
      initializeItems();
    } else {
      state.items = [];
    }

    updateValueDisplays();
    updateSummary();
    updateOverview();
    updateActionsDataset();
    refreshExpiryFieldDisplay();

    closeButtons.forEach((button) => button.addEventListener('click', closeModal));
    document.addEventListener('keydown', handleGlobalKeyDown);

    if (cancelButton) {
      cancelButton.addEventListener('click', handleCancel);
    }

    if (saveButton) {
      saveButton.addEventListener('click', handleConfirm);
    }

    if (tipsToggle && tipsPanel) {
      tipsToggle.addEventListener('click', () => {
        tipsPanel.classList.toggle('is-visible');
      });
    }

    if (tipsClose && tipsPanel) {
      tipsClose.addEventListener('click', () => {
        tipsPanel.classList.remove('is-visible');
      });
    }

    if (confirmSecondaryBtn) {
      confirmSecondaryBtn.addEventListener('click', () => {
        closeConfirmDialog();
      });
    }

    if (confirmPrimaryBtn) {
      confirmPrimaryBtn.addEventListener('click', () => {
        const current = confirmState;
        closeConfirmDialog();
        if (current && typeof current.onConfirm === 'function') {
          current.onConfirm();
        }
      });
    }

    if (confirmDismissBtn) {
      confirmDismissBtn.addEventListener('click', () => {
        closeConfirmDialog();
      });
    }

    if (confirmRoot) {
      confirmRoot.addEventListener('click', (event) => {
        if (!confirmCard || confirmCard.contains(event.target)) {
          return;
        }
        closeConfirmDialog();
      });

      confirmRoot.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
          event.preventDefault();
          closeConfirmDialog();
        }

        if (event.key === 'Tab') {
          trapFocusInConfirm(event);
        }
      });
    }

    function getLocaleForCurrency(code) {
    const map = {
      BRL: 'pt-BR',
      EUR: 'de-DE',
      GBP: 'en-GB',
      UK: 'en-GB',
      USD: 'en-US',
    };
    return map[code] || 'pt-BR';
  }

  function normalizeItem(item) {
    return {
      name: typeof item?.name === 'string' ? item.name : '',
      quantity: toNumber(item?.quantity ?? 1) || 1,
      value: toNumber(item?.value ?? 0),
    };
  }

  function toNumber(value) {
    if (typeof value === 'number' && Number.isFinite(value)) {
      return value;
    }
    if (value === null || value === undefined) {
      return 0;
    }
    const parsed = parseFloat(
      String(value)
        .replace(/\s/g, '')
        .replace(/,(?=\d{3}(?:\D|$))/g, '')
        .replace(',', '.')
    );
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function computeItemsTotal(items) {
    return (items || []).reduce((sum, item) => {
      const quantity = toNumber(item?.quantity ?? 0);
      const value = toNumber(item?.value ?? 0);
      return sum + quantity * value;
    }, 0);
  }

  function isFieldRelevant(el) {
    const wrapper = el.closest('[data-only]');
    return !wrapper || wrapper.dataset.only === type;
  }

  function setupField(el) {
    const field = el.dataset.field;
    const isMultiline = el.classList.contains('edit-card__multiline');
    el.addEventListener('focus', () => {
      if (el.isContentEditable) {
        placeCaretAtEnd(el);
      }
    });
    el.addEventListener('keydown', (event) => handleKeydown(event, isMultiline));
    el.addEventListener('input', () => handleFieldInput(field, el));
    el.addEventListener('blur', () => handleFieldBlur(field, el));
  }

  function handleKeydown(event, isMultiline) {
    if (event.key === 'Enter' && !isMultiline) {
      event.preventDefault();
      (event.target).blur();
    }
  }

  function handleFieldInput(field, el) {
    const raw = el.textContent || '';

    switch (field) {
      case 'value': {
        state.value = parseCurrency(raw);
        manualValueOverride = true;
        break;
      }
      case 'discount': {
        state.discount = parseCurrency(raw);
        syncDetailedTotals({ skipDiscountFormatting: true });
        break;
      }
      case 'expiry_date': {
        const { display, normalized, digits } = formatDateInput(raw);
        state.expiry_date = normalized || digits || '';
        setDateFieldContent(el, display);
        break;
      }
      case 'notes': {
        state.notes = sanitizeMultiline(raw, true);
        break;
      }
      case 'service_description': {
        state.service_description = sanitizeMultiline(raw, true);
        break;
      }
      case 'address': {
        state.address = sanitizeMultiline(raw, true);
        break;
      }
      case 'client_name': {
        state.client_name = sanitizeText(raw);
        break;
      }
      case 'phone': {
        state.phone = raw.replace(/\s+/g, ' ').trim();
        break;
      }
      default: {
        state[field] = sanitizeText(raw);
      }
    }

    updateSummary();
    updateOverview();
    updateActionsDataset();
  }

  function syncDetailedTotals(context = {}) {
    if (type !== 'detailed') {
      return;
    }
    const itemsTotal = Number.isFinite(context.itemsTotal)
      ? context.itemsTotal
      : computeItemsTotal(state.items);
    const discountAmount = Number.isFinite(state.discount) ? state.discount : 0;
    state.value = Math.max(itemsTotal - discountAmount, 0);
    updateValueDisplays({ skipDiscount: !!context.skipDiscountFormatting });
    updateSummary();
    updateOverview();
    updateActionsDataset();
  }

  function handleFieldBlur(field, el) {
    if (field === 'value') {
      el.textContent = formatNumber(state.value);
    } else if (field === 'discount') {
      el.textContent = formatNumber(state.discount);
      syncDetailedTotals();
    } else if (field === 'expiry_date') {
      const normalized = sanitizeDate(state.expiry_date);
      state.expiry_date = normalized || '';
      el.textContent = formatDateForDisplay(state.expiry_date);
      updateSummary();
      updateOverview();
      updateActionsDataset();
      return;
    } else if (el.classList.contains('edit-card__multiline')) {
      el.textContent = sanitizeMultiline(el.textContent || '', true);
    } else {
      el.textContent = sanitizeText(el.textContent || '');
    }
  }

  function sanitizeText(value) {
    if (typeof value !== 'string') {
      return '';
    }
    return value.replace(/\s+/g, ' ').trim();
  }

  function sanitizeMultiline(value, allowEmptyLine) {
    if (typeof value !== 'string') {
      return '';
    }
    const lines = value.split(/\r?\n/).map((line) => line.trim());
    const filtered = allowEmptyLine ? lines : lines.filter((line) => line.length);
    return filtered.join('\n').trim();
  }

  function sanitizeDate(value) {
    return normalizeDate(value);
  }

  function formatDateForDisplay(value) {
    const normalized = normalizeDate(value);
    if (!normalized) {
      return '';
    }
    const [year, month, day] = normalized.split('-');
    return `${day}/${month}/${String(year).slice(-2)}`;
  }

  function formatDateInput(value) {
    if (value === null || value === undefined) {
      return { display: '', normalized: '', digits: '' };
    }

    const digits = String(value).replace(/\D/g, '').slice(0, 8);
    if (!digits) {
      return { display: '', normalized: '', digits: '' };
    }

    const parts = [];
    const day = digits.slice(0, 2);
    if (day) {
      parts.push(day);
    }
    const month = digits.slice(2, 4);
    if (month) {
      parts.push(month);
    }
    const year = digits.slice(4, 6);
    if (year) {
      parts.push(year);
    }

    const display = parts.join('/');
    const normalized = normalizeDate(display);

    return { display, normalized, digits };
  }

  function normalizeDateForPayload(value, options = {}) {
    const { nullIfEmpty = true } = options;
    const normalized = normalizeDate(value);
    if (!normalized) {
      return nullIfEmpty ? null : '';
    }
    return normalized;
  }

  function normalizeDate(value) {
    if (value === null || value === undefined) {
      return '';
    }

    const raw = String(value).trim();
    if (!raw) {
      return '';
    }

    const compact = raw.replace(/[./]/g, '-');
    const isoMatch = compact.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
    if (isoMatch) {
      const year = Number(isoMatch[1]);
      const month = Number(isoMatch[2]);
      const day = Number(isoMatch[3]);
      if (isValidDateComponents(year, month, day)) {
        return `${String(year).padStart(4, '0')}-${padNumber(month)}-${padNumber(day)}`;
      }
      return '';
    }

    const dmyMatch = compact.match(/^(\d{1,2})-(\d{1,2})-(\d{4})$/);
    if (dmyMatch) {
      const day = Number(dmyMatch[1]);
      const month = Number(dmyMatch[2]);
      const year = Number(dmyMatch[3]);
      if (isValidDateComponents(year, month, day)) {
        return `${String(year).padStart(4, '0')}-${padNumber(month)}-${padNumber(day)}`;
      }
      return '';
    }

    const parts = compact.split('-').filter(Boolean);
    if (parts.length === 3) {
      const [first, second, third] = parts;
      if (first.length === 4) {
        const year = Number(first);
        const month = Number(second);
        const day = Number(third);
        if (isValidDateComponents(year, month, day)) {
          return `${String(year).padStart(4, '0')}-${padNumber(month)}-${padNumber(day)}`;
        }
      } else if (third.length === 4) {
        const day = Number(first);
        const month = Number(second);
        const year = Number(third);
        if (isValidDateComponents(year, month, day)) {
          return `${String(year).padStart(4, '0')}-${padNumber(month)}-${padNumber(day)}`;
        }
      }
    }

    const digits = compact.replace(/\D/g, '');
    if (digits.length === 8) {
      const firstFour = Number(digits.slice(0, 4));
      let year;
      let month;
      let day;
      if (firstFour >= 1900) {
        year = firstFour;
        month = Number(digits.slice(4, 6));
        day = Number(digits.slice(6, 8));
      } else {
        day = Number(digits.slice(0, 2));
        month = Number(digits.slice(2, 4));
        year = Number(digits.slice(4, 8));
      }

      if (isValidDateComponents(year, month, day)) {
        return `${String(year).padStart(4, '0')}-${padNumber(month)}-${padNumber(day)}`;
      }
      return '';
    }

    if (digits.length === 6) {
      const first = Number(digits.slice(0, 2));
      const middle = Number(digits.slice(2, 4));
      const last = Number(digits.slice(4, 6));
      let year;
      let month;
      let day;

      if (first > 31) {
        year = resolveTwoDigitYear(first);
        month = middle;
        day = last;
      } else {
        day = first;
        month = middle;
        year = resolveTwoDigitYear(last);
      }

      if (isValidDateComponents(year, month, day)) {
        return `${String(year).padStart(4, '0')}-${padNumber(month)}-${padNumber(day)}`;
      }
      return '';
    }

    return '';
  }

  function isValidDateComponents(year, month, day) {
    if (!Number.isFinite(year) || !Number.isFinite(month) || !Number.isFinite(day)) {
      return false;
    }
    if (year < 1900 || month < 1 || month > 12 || day < 1 || day > 31) {
      return false;
    }
    const date = new Date(Date.UTC(year, month - 1, day));
    return (
      date.getUTCFullYear() === year &&
      date.getUTCMonth() === month - 1 &&
      date.getUTCDate() === day
    );
  }

  function resolveTwoDigitYear(value) {
    const year = Number(value);
    if (!Number.isFinite(year)) {
      return NaN;
    }
    if (year >= 70) {
      return 1900 + year;
    }
    return 2000 + year;
  }

  function padNumber(value) {
    return String(value).padStart(2, '0');
  }

  function refreshExpiryFieldDisplay() {
    if (!expiryField) {
      return;
    }
    const display = formatDateForDisplay(state.expiry_date);
    setDateFieldContent(expiryField, display);
  }

  function setDateFieldContent(el, display) {
    if (!el) {
      return;
    }
    const text = typeof display === 'string' ? display : '';
    if (el.textContent === text) {
      return;
    }

    const shouldRestoreCaret = document.activeElement === el;
    el.textContent = text;

    if (shouldRestoreCaret) {
      placeCaretAtEnd(el);
    }
  }

  function placeCaretAtEnd(el) {
    if (!el || typeof document.getSelection !== 'function') {
      return;
    }
    try {
      const selection = document.getSelection();
      if (!selection) {
        return;
      }
      const range = document.createRange();
      range.selectNodeContents(el);
      range.collapse(false);
      selection.removeAllRanges();
      selection.addRange(range);
    } catch (error) {
      console.warn('edit_quotation_modal: unable to place caret', error);
    }
  }

  function parseCurrency(value) {
    if (typeof value === 'number' && Number.isFinite(value)) {
      return value;
    }
    if (typeof value !== 'string') {
      value = String(value ?? '');
    }
    let cleaned = value.replace(/[^0-9,.-]/g, '');
    if (!cleaned) {
      return 0;
    }
    const lastComma = cleaned.lastIndexOf(',');
    const lastDot = cleaned.lastIndexOf('.');
    if (lastComma > -1 && lastDot > -1) {
      if (lastComma > lastDot) {
        cleaned = cleaned.replace(/\./g, '').replace(',', '.');
      } else {
        cleaned = cleaned.replace(/,/g, '');
      }
    } else if (lastComma > -1) {
      cleaned = cleaned.replace(',', '.');
    }
    const parsed = parseFloat(cleaned);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function parseNumber(value) {
    if (typeof value === 'number' && Number.isFinite(value)) {
      return value;
    }
    if (typeof value !== 'string') {
      value = String(value ?? '');
    }
    const cleaned = value.replace(/[^0-9,.-]/g, '').replace(',', '.');
    const parsed = parseFloat(cleaned);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function formatNumber(value) {
    return numberFormatter.format(Number.isFinite(value) ? value : 0);
  }

  function formatPlainNumber(value) {
    const numeric = Number.isFinite(value) ? Number(value) : 0;
    return numeric.toFixed(2);
  }

  function formatQuantity(value) {
    const numeric = Number.isFinite(value) ? value : 0;
    return quantityFormatter.format(numeric || 0);
  }

  function updateValueDisplays(options = {}) {
    const { skipDiscount = false } = options;
    if (valueField) {
      valueField.textContent = formatNumber(state.value);
    }
    if (!skipDiscount && discountField && isFieldRelevant(discountField)) {
      discountField.textContent = formatNumber(state.discount);
    }
  }

  function updateSummary() {
    if (summaryClientEl) {
      summaryClientEl.textContent = state.client_name?.trim() || '—';
    }
    if (summaryValueEl) {
      summaryValueEl.textContent = formatNumber(state.value);
    }
    if (summaryExpiryEl) {
      summaryExpiryEl.textContent = formatDateForDisplay(state.expiry_date) || '-';
    }
  }

  function updateOverview() {
    if (overviewValueEl) {
      overviewValueEl.textContent = formatNumber(state.value);
    }
    if (overviewExpiryEl) {
      overviewExpiryEl.textContent = formatDateForDisplay(state.expiry_date) || '-';
    }
    if (overviewDiscountEl && type === 'detailed') {
      overviewDiscountEl.textContent = formatNumber(state.discount);
    }
  }

  function updateActionsDataset() {
    if (!qaActions) {
      return;
    }
    qaActions.dataset.totalValue = formatPlainNumber(state.value);
  }

  function openConfirmDialog(options = {}) {
    if (!confirmRoot || !confirmMessageEl || !confirmPrimaryBtn || !confirmSecondaryBtn) {
      if (typeof options.onConfirm === 'function') {
        options.onConfirm();
      }
      return;
    }

    if (confirmState) {
      closeConfirmDialog();
    }

    confirmState = {
      onConfirm: typeof options.onConfirm === 'function' ? options.onConfirm : null,
      returnFocus:
        options.returnFocus && typeof options.returnFocus.focus === 'function'
          ? options.returnFocus
          : null,
    };

    confirmMessageEl.textContent = options.message || 'Deseja confirmar esta ação?';
    confirmPrimaryBtn.textContent = options.primaryLabel || 'Confirmar';
    confirmSecondaryBtn.textContent = options.secondaryLabel || 'Cancelar';

    if (options.intent) {
      confirmRoot.dataset.intent = options.intent;
    } else {
      delete confirmRoot.dataset.intent;
    }

    previousActiveElement = document.activeElement;
    confirmRoot.removeAttribute('hidden');
    requestAnimationFrame(() => {
      confirmRoot.classList.add('is-visible');
      modal.classList.add('has-confirm-open');
      confirmPrimaryBtn.focus();
    });
  }

  function closeConfirmDialog() {
    if (!confirmRoot) {
      confirmState = null;
      return;
    }

    confirmRoot.classList.remove('is-visible');
    delete confirmRoot.dataset.intent;
    confirmRoot.setAttribute('hidden', 'hidden');
    modal.classList.remove('has-confirm-open');

    const focusTarget = confirmState?.returnFocus;
    confirmState = null;
    if (focusTarget && typeof focusTarget.focus === 'function') {
      focusTarget.focus();
    } else if (previousActiveElement && typeof previousActiveElement.focus === 'function') {
      previousActiveElement.focus();
    }
    previousActiveElement = null;
  }

  function trapFocusInConfirm(event) {
    if (!confirmCard) {
      return;
    }
    const focusableSelectors = [
      'button:not([disabled])',
      '[href]',
      'input:not([disabled])',
      'select:not([disabled])',
      'textarea:not([disabled])',
      '[tabindex]:not([tabindex="-1"])',
    ];
    const focusable = Array.from(confirmCard.querySelectorAll(focusableSelectors.join(','))).filter(
      (el) => el.offsetParent !== null
    );
    if (!focusable.length) {
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
      return;
    }
    if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function initializeItems() {
    const rows = getItemRows();
    if (!rows.length) {
      createItemRow();
    } else {
      rows.forEach(attachItemListeners);
      rows.forEach(updateItemRowSubtotal);
    }
    if (addItemButton) {
      addItemButton.addEventListener('click', () => {
        const row = createItemRow();
        const nameField = row.querySelector('[data-item-field="name"]');
        if (nameField) {
          nameField.focus();
        }
      });
    }
    recalcItems();
  }

  function getItemRows() {
    if (!itemsRoot) {
      return [];
    }
    return Array.from(itemsRoot.querySelectorAll('[data-item-row]'));
  }

  function attachItemListeners(row) {
    if (row.dataset.enhanced === 'true') {
      return;
    }
    row.dataset.enhanced = 'true';

    const nameField = row.querySelector('[data-item-field="name"]');
    const quantityField = row.querySelector('[data-item-field="quantity"]');
    const valueFieldEl = row.querySelector('[data-item-field="value"]');
    const removeButton = row.querySelector('[data-action="remove-item"]');

    if (nameField) {
      nameField.addEventListener('keydown', (event) => handleKeydown(event, false));
      nameField.addEventListener('input', () => handleItemChange(row));
      nameField.addEventListener('blur', () => {
        nameField.textContent = sanitizeText(nameField.textContent || '');
        handleItemChange(row);
      });
    }

    if (quantityField) {
      quantityField.addEventListener('keydown', (event) => handleKeydown(event, false));
      quantityField.addEventListener('input', () => handleItemChange(row));
      quantityField.addEventListener('blur', () => {
        const quantity = parseNumber(quantityField.textContent || '') || 0;
        quantityField.textContent = formatQuantity(quantity || 0);
        handleItemChange(row);
      });
    }

    if (valueFieldEl) {
      valueFieldEl.addEventListener('keydown', (event) => handleKeydown(event, false));
      valueFieldEl.addEventListener('input', () => handleItemChange(row));
      valueFieldEl.addEventListener('blur', () => {
        const amount = parseCurrency(valueFieldEl.textContent || '');
        valueFieldEl.textContent = formatNumber(amount);
        handleItemChange(row);
      });
    }

    if (removeButton) {
      removeButton.addEventListener('click', () => {
        row.remove();
        recalcItems();
      });
    }
  }

  function handleItemChange(row) {
    updateItemRowSubtotal(row);
    recalcItems({ autoSyncValue: !manualValueOverride });
  }

  function updateItemRowSubtotal(row) {
    const subtotalEl = row.querySelector('[data-subtotal]');
    if (!subtotalEl) {
      return;
    }
    const { quantity, value } = extractItem(row);
    subtotalEl.textContent = formatNumber(quantity * value);
  }

  function extractItem(row) {
    const nameField = row.querySelector('[data-item-field="name"]');
    const quantityField = row.querySelector('[data-item-field="quantity"]');
    const valueFieldEl = row.querySelector('[data-item-field="value"]');

    return {
      name: sanitizeText(nameField?.textContent || ''),
      quantity: parseNumber(quantityField?.textContent || '') || 0,
      value: parseCurrency(valueFieldEl?.textContent || ''),
    };
  }

  function createItemRow(initial = { name: '', quantity: 1, value: 0 }) {
    if (!itemsRoot) {
      throw new Error('itemsRoot not found');
    }
    const row = document.createElement('div');
    row.className = 'edit-card__items-row';
    row.setAttribute('data-item-row', '');
    row.innerHTML = `
      <span class="edit-card__item edit-card__item--name" contenteditable data-item-field="name" data-placeholder="Descrição do item">${
        sanitizeHTML(initial.name || '')
      }</span>
      <span class="edit-card__item edit-card__item--quantity" contenteditable data-item-field="quantity" data-type="number">${formatQuantity(
        initial.quantity ?? 1
      )}</span>
      <span class="edit-card__item edit-card__item--value" contenteditable data-item-field="value" data-type="currency">${formatNumber(
        initial.value ?? 0
      )}</span>
      <span class="edit-card__item edit-card__item--subtotal" data-subtotal>${formatNumber(
        (initial.quantity || 0) * (initial.value || 0)
      )}</span>
      <button type="button" class="edit-card__item-remove" data-action="remove-item" aria-label="Remover item">&times;</button>
    `;
    itemsRoot.appendChild(row);
    attachItemListeners(row);
    return row;
  }

  function sanitizeHTML(value) {
    const temp = document.createElement('div');
    temp.textContent = value;
    return temp.innerHTML;
  }

  function recalcItems(options = {}) {
    const { autoSyncValue = true } = options;
    if (!itemsRoot) {
      state.items = [];
      return;
    }
    const rows = getItemRows();
    const items = rows.map(extractItem).filter((item) => item.name || item.value || item.quantity);
    state.items = items;
    const total = computeItemsTotal(items);

    if (type === 'detailed' && autoSyncValue) {
      syncDetailedTotals({ itemsTotal: total });
    }

    updateSummary();
    updateOverview();
    updateActionsDataset();
  }

  function buildPayload() {
    const payload = {
      client_name: normalizeTextForPayload(state.client_name, { nullIfEmpty: false }),
      phone: normalizeTextForPayload(state.phone),
      value: Number.isFinite(state.value) ? Number(state.value) : 0,
      expiry_date: normalizeDateForPayload(state.expiry_date),
      notes: normalizeTextForPayload(state.notes, { allowMultiline: true, nullIfEmpty: false }),
    };

    if (type === 'quick') {
      payload.service_description = normalizeTextForPayload(state.service_description, {
        allowMultiline: true,
        nullIfEmpty: false,
      });
    }

    if (type === 'detailed') {
      payload.address = normalizeTextForPayload(state.address, {
        allowMultiline: true,
        nullIfEmpty: false,
      });
      payload.discount = Number.isFinite(state.discount) ? Number(state.discount) : 0;
      payload.items = state.items.map((item) => ({
        name: normalizeTextForPayload(item.name, { nullIfEmpty: false }) || '',
        quantity: Number.isFinite(item.quantity) ? Number(item.quantity) : 0,
        value: Number.isFinite(item.value) ? Number(item.value) : 0,
      }));
    }

    return Object.fromEntries(
      Object.entries(payload).filter(([_, value]) => value !== undefined)
    );
  }

  function normalizeTextForPayload(value, options = {}) {
    const { nullIfEmpty = true, allowMultiline = false } = options;
    if (value === null || value === undefined) {
      return nullIfEmpty ? null : '';
    }
    const normalised = allowMultiline
      ? sanitizeMultiline(String(value), true)
      : sanitizeText(String(value));
    if (!normalised) {
      return nullIfEmpty ? null : '';
    }
    return normalised;
  }

  function handleConfirm(event) {
    event.preventDefault();
    openConfirmDialog({
      message: 'Deseja confirmar as alterações deste orçamento?',
      primaryLabel: 'Confirmar',
      secondaryLabel: 'Revisar',
      intent: 'primary',
      returnFocus: event.currentTarget,
      onConfirm: executeSave,
    });
  }

  function handleCancel(event) {
    event.preventDefault();
    openConfirmDialog({
      message: 'Descartar as alterações e sair da edição?',
      primaryLabel: 'Descartar',
      secondaryLabel: 'Continuar editando',
      intent: 'danger',
      returnFocus: event.currentTarget,
      onConfirm: () => {
        closeModal();
      },
    });
  }

  function executeSave() {
    if (!saveEndpoint) {
      console.warn('edit_quotation_modal: save endpoint not provided');
      return;
    }

    if (type === 'detailed') {
      recalcItems({ autoSyncValue: !manualValueOverride });
    }

    const payload = buildPayload();
    setLoading(true);

    fetch(saveEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
      .then(async (response) => {
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.success) {
          const message = data.error || 'Não foi possível salvar o orçamento.';
          throw new Error(message);
        }
        closeModal();
        window.location.reload();
      })
      .catch((error) => {
        alert(error.message || 'Erro ao salvar o orçamento.');
      })
      .finally(() => {
        setLoading(false);
      });
  }

  function setLoading(isLoading) {
    if (!saveButton) {
      return;
    }
    if (isLoading) {
      saveButton.classList.add('is-loading');
      saveButton.setAttribute('disabled', 'disabled');
      saveButton.setAttribute('aria-busy', 'true');
    } else {
      saveButton.classList.remove('is-loading');
      saveButton.removeAttribute('disabled');
      saveButton.removeAttribute('aria-busy');
    }
  }

  function openModal() {
    modal.classList.add('is-open');
    modal.setAttribute('aria-hidden', 'false');
    setTimeout(() => {
      const firstField = fieldElements[0];
      if (firstField) {
        firstField.focus();
      }
    }, 0);
  }

  function closeModal() {
    modal.classList.remove('is-open');
    modal.setAttribute('aria-hidden', 'true');
    modal.blur();
    closeConfirmDialog();
    const tipsPanel = modal.querySelector('[data-tips-panel]');
    if (tipsPanel) {
      tipsPanel.classList.remove('is-visible');
    }
  }

  function handleGlobalKeyDown(event) {
    if (event.key === 'Escape' && modal.classList.contains('is-open')) {
      closeModal();
    }
  }

  const scriptCache = new Map();

  function loadScriptOnce(src) {
    if (scriptCache.has(src)) {
      return scriptCache.get(src);
    }
    const promise = new Promise((resolve, reject) => {
      const existing = Array.from(document.querySelectorAll('script')).find(
        (tag) => tag.src === src
      );
      if (existing && existing.dataset.loaded === 'true') {
        resolve();
        return;
      }
      const script = existing || document.createElement('script');
      script.src = src;
      script.crossOrigin = 'anonymous';
      script.referrerPolicy = 'no-referrer';
      script.async = false;
      script.onload = () => {
        script.dataset.loaded = 'true';
        resolve();
      };
      script.onerror = () => reject(new Error(`Falha ao carregar script: ${src}`));
      if (!existing) {
        document.head.appendChild(script);
      }
    });
    scriptCache.set(src, promise);
    return promise;
  }

  async function ensureHtml2Canvas() {
    if (typeof window.html2canvas === 'function') {
      return window.html2canvas;
    }
    const fallbackSrc = 'https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js';
    await loadScriptOnce(fallbackSrc);
    if (typeof window.html2canvas !== 'function') {
      throw new Error('html2canvas indisponível.');
    }
    return window.html2canvas;
  }

  async function ensureJsPDF() {
    const { jspdf } = window;
    if (jspdf && typeof jspdf.jsPDF === 'function') {
      return jspdf.jsPDF;
    }
    const fallbackSrc = 'https://cdn.jsdelivr.net/npm/jspdf@2.5.1/dist/jspdf.umd.min.js';
    await loadScriptOnce(fallbackSrc);
    if (window.jspdf && typeof window.jspdf.jsPDF === 'function') {
      return window.jspdf.jsPDF;
    }
    throw new Error('jsPDF indisponível.');
  }

  async function renderCanvas() {
    const html2canvas = await ensureHtml2Canvas();
    const target = document.getElementById('quotationContainer');
    if (!target) {
      throw new Error('Elemento do orçamento não encontrado para captura.');
    }
    if (document.fonts && typeof document.fonts.ready?.then === 'function') {
      try {
        await document.fonts.ready;
      } catch (error) {
        console.warn('renderCanvas: fonts not fully ready', error);
      }
    }

    const clone = target.cloneNode(true);
    const originalId = target.id || 'quotationContainer';
    const temporaryId = `${originalId}__source`;
    clone.id = originalId;
    if (target.id) {
      target.id = temporaryId;
    }
    clone.classList.add('is-export-clone');
    clone.classList.remove('is-open');
    clone.classList.remove('has-confirm-open');
    clone.querySelectorAll('[data-confirm-root]').forEach((node) => {
      node.remove();
    });
    clone.querySelectorAll('.is-visible').forEach((node) => node.classList.remove('is-visible'));
    clone.querySelectorAll('[data-hydrated]').forEach((node) => node.removeAttribute('data-hydrated'));
    const targetRect = target.getBoundingClientRect();
    const computed = getComputedStyle(target);
    const breakpointWidth = (() => {
      const stylesheetWidth = parseFloat(target.dataset.exportWidth || '0');
      if (Number.isFinite(stylesheetWidth) && stylesheetWidth > 0) {
        return stylesheetWidth;
      }
      const cssVars = getComputedStyle(document.documentElement);
      const customWidth = parseFloat(cssVars.getPropertyValue('--quotation-export-width') || '0');
      if (Number.isFinite(customWidth) && customWidth > 0) {
        return customWidth;
      }
      const inlineStyleWidth = parseFloat(target.style.width || '0');
      if (Number.isFinite(inlineStyleWidth) && inlineStyleWidth > 0) {
        return inlineStyleWidth;
      }
      return 0;
    })();

    const maxWidthValue = parseFloat(computed.maxWidth);
    const widthValue = parseFloat(computed.width);
    let exportWidth = breakpointWidth
      || (Number.isFinite(maxWidthValue) && computed.maxWidth.endsWith('px') ? maxWidthValue : 0)
      || (Number.isFinite(widthValue) && computed.width.endsWith('px') ? widthValue : 0)
      || Math.max(targetRect.width, 820);

    exportWidth = Math.max(exportWidth, 600);

    const wrapper = document.createElement('div');
    wrapper.className = 'quotation-export-wrapper';
    wrapper.style.position = 'fixed';
    wrapper.style.top = '0';
    wrapper.style.left = '-10000px';
    wrapper.style.width = `${exportWidth}px`;
    wrapper.style.maxWidth = `${exportWidth}px`;
    wrapper.style.pointerEvents = 'none';
    wrapper.style.opacity = '0';
    wrapper.style.zIndex = '-1';
    wrapper.style.background = getComputedStyle(document.body).backgroundColor;

    clone.style.position = 'static';
    clone.style.margin = '0';
    clone.style.width = '100%';
    clone.style.maxWidth = 'none';
    clone.style.minWidth = '100%';
    clone.style.maxHeight = 'none';
    clone.style.pointerEvents = 'none';
    clone.style.opacity = '1';
    clone.style.transform = 'none';
    clone.style.background = computed.backgroundColor;

    wrapper.appendChild(clone);
    document.body.appendChild(wrapper);

    await new Promise((resolve) => requestAnimationFrame(resolve));
    const cloneRect = clone.getBoundingClientRect();
    if (cloneRect.width && Math.abs(cloneRect.width - exportWidth) > 1) {
      exportWidth = cloneRect.width;
      wrapper.style.width = `${exportWidth}px`;
      wrapper.style.maxWidth = `${exportWidth}px`;
    }

    const parentBackground = target.parentElement
      ? getComputedStyle(target.parentElement).backgroundColor
      : null;
    const bodyBackground = getComputedStyle(document.body).backgroundColor;
    const backgroundColor =
      parentBackground && parentBackground !== 'rgba(0, 0, 0, 0)'
        ? parentBackground
        : bodyBackground && bodyBackground !== 'rgba(0, 0, 0, 0)'
          ? bodyBackground
          : '#ffffff';

    try {
      return await html2canvas(clone, {
        backgroundColor,
        scale: Math.min(2, window.devicePixelRatio || 1.5),
        useCORS: true,
        removeContainer: true,
      });
    } finally {
      wrapper.remove();
      if (target.id === temporaryId) {
        target.id = originalId;
      }
    }
  }

  async function downloadImage() {
    try {
      const canvas = await renderCanvas();
      const link = document.createElement('a');
      const code = (root.dataset.quotationId || '').slice(0, 8).toUpperCase() || 'ORCAMENTO';
      link.download = `orcamento-${code}.png`;
      link.href = canvas.toDataURL('image/png');
      link.click();
    } catch (error) {
      console.error(error);
      alert('Não foi possível gerar a imagem do orçamento.');
    }
  }

  async function downloadPDF() {
    try {
      const jsPDF = await ensureJsPDF();
      const canvas = await renderCanvas();
      const imgData = canvas.toDataURL('image/png');
      const pdf = new jsPDF('p', 'mm', 'a4');
      const pageWidth = pdf.internal.pageSize.getWidth();
      const pageHeight = pdf.internal.pageSize.getHeight();
      const imageWidth = canvas.width;
      const imageHeight = canvas.height;
      const scale = Math.min(pageWidth / imageWidth, pageHeight / imageHeight);
      const renderWidth = imageWidth * scale;
      const renderHeight = imageHeight * scale;
      const marginX = (pageWidth - renderWidth) / 2;
      const marginY = Math.max(10, (pageHeight - renderHeight) / 2);
      pdf.addImage(imgData, 'PNG', marginX, marginY, renderWidth, renderHeight);
      const code = (root.dataset.quotationId || '').slice(0, 8).toUpperCase() || 'ORCAMENTO';
      pdf.save(`orcamento-${code}.pdf`);
    } catch (error) {
      console.error(error);
      alert('Não foi possível gerar o PDF do orçamento.');
    }
  }

    function shareQuotation() {
    const total = `${currencySymbol} ${formatNumber(state.value)}`;
    const client = state.client_name || 'cliente';
    const shareData = {
      title: `Orçamento ${client}`,
      text: `Orçamento no valor de ${total}`,
      url: window.location.href,
    };

    if (navigator.share) {
      navigator.share(shareData).catch(() => {});
      return;
    }

    navigator.clipboard
      ?.writeText(window.location.href)
      .then(() => {
        alert('Link copiado para a área de transferência.');
      })
      .catch(() => {
        alert('Copie o link manualmente: ' + window.location.href);
      });
    }
  } catch (error) {
    console.error('edit_quotation_modal: failed to initialize', error);
    if (!handlersAssigned) {
      window.openEditModal = previousHandlers.open || noop;
      window.closeEditModal = previousHandlers.close || noop;
      window.downloadImage = previousHandlers.image || noop;
      window.downloadPDF = previousHandlers.pdf || noop;
      window.shareQuotation = previousHandlers.share || noop;
    }
  }
})();
