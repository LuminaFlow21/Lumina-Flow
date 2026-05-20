(function() {
  function enhanceToolbar() {
    const toolbar = document.querySelector('.action-buttons');
    if (!toolbar || toolbar.dataset.enhanced === 'true') {
      return null;
    }

    toolbar.dataset.enhanced = 'true';
    toolbar.id = 'quotationToolbar';

    const hint = document.createElement('p');
    hint.className = 'action-buttons__hint';
    hint.textContent = 'mexa na tela para ver o orçamento';

    const bar = document.createElement('div');
    bar.className = 'action-buttons__bar';

    while (toolbar.firstChild) {
      bar.appendChild(toolbar.firstChild);
    }

    toolbar.appendChild(hint);
    toolbar.appendChild(bar);

    document.body.classList.add('quotation-viewer');
    return toolbar;
  }

  function ensureViewportScroller() {
    const quotation = document.getElementById('quotationContainer') || document.querySelector('.orcamento');
    if (!quotation) {
      return;
    }

    let viewportPan = quotation.closest('.viewport-pan');
    if (!viewportPan) {
      viewportPan = document.createElement('div');
      viewportPan.className = 'viewport-pan';

      const parent = quotation.parentNode;
      if (parent) {
        parent.insertBefore(viewportPan, quotation);
        viewportPan.appendChild(quotation);
      }
    }

    if (!document.querySelector('.mobile-scroll-hint')) {
      const hint = document.createElement('div');
      hint.className = 'mobile-scroll-hint';
      hint.textContent = '👆 mexa na tela para ver o orçamento';

      const insertionTarget = viewportPan.parentNode;
      if (insertionTarget) {
        insertionTarget.insertBefore(hint, viewportPan);
      }
    }
  }

  function withToolbarHidden(callback) {
    const toolbar = document.getElementById('quotationToolbar') || document.querySelector('.action-buttons');
    const bar = toolbar ? toolbar.querySelector('.action-buttons__bar') : null;

    if (!toolbar) {
      return callback();
    }

    const previousDisplay = toolbar.style.display;
    toolbar.style.display = 'none';
    const result = callback();

    return Promise.resolve(result).finally(() => {
      toolbar.style.display = previousDisplay || '';
      if (bar && bar.style.display === 'none') {
        bar.style.display = '';
      }
    });
  }

  window.LuminaFlow = window.LuminaFlow || {};
  window.LuminaFlow.enhanceQuotationToolbar = enhanceToolbar;
  window.LuminaFlow.withToolbarHidden = withToolbarHidden;
  window.LuminaFlow.ensureViewportScroller = ensureViewportScroller;

  document.addEventListener('DOMContentLoaded', () => {
    enhanceToolbar();
    ensureViewportScroller();
  }, { once: true });
})();
