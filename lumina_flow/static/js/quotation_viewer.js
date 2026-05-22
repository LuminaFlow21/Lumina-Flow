(function() {
  const SCALE_BASE_WIDTH = 760;
  const MIN_VIEWER_SCALE = 0.1;
  const MAX_VIEWER_SCALE = 3;
  const responsiveScaleState = new WeakMap();

  function clampScale(value, state) {
    const min = state?.min ?? MIN_VIEWER_SCALE;
    const max = state?.max ?? MAX_VIEWER_SCALE;
    return Math.min(max, Math.max(min, value));
  }

  function computeAutoScale(target) {
    const viewport = target.closest('.viewport-pan');
    const availableWidth = viewport ? viewport.clientWidth : target.clientWidth || window.innerWidth;
    const ratio = availableWidth / SCALE_BASE_WIDTH;
    return clampScale(Math.min(1, ratio));
  }

  function updateBaseMetrics(target) {
    const baseWidth = target.offsetWidth || target.getBoundingClientRect().width || SCALE_BASE_WIDTH;
    const baseHeight = target.scrollHeight || target.offsetHeight || target.getBoundingClientRect().height || 0;
    target.dataset.viewerBaseWidth = String(baseWidth);
    target.dataset.viewerBaseHeight = String(baseHeight);
    return { baseWidth, baseHeight };
  }

  function applyScaleValue(target, totalScale) {
    const state = responsiveScaleState.get(target);
    const clamped = clampScale(totalScale, state);
    const scaleValue = clamped.toFixed(3);
    target.style.setProperty('--viewer-scale', scaleValue);

    const body = document.body;
    if (body) {
      if (Math.abs(clamped - 1) > 0.01) {
        body.classList.add('is-scaled');
      } else {
        body.classList.remove('is-scaled');
      }
    }

    const { baseWidth, baseHeight } = updateBaseMetrics(target);

    const layoutShell = target.closest('.layout-shell');
    if (layoutShell) {
      layoutShell.style.setProperty('--viewer-scale', scaleValue);
      layoutShell.style.setProperty('--viewer-base-width', `${baseWidth}px`);
    }

    const viewportPan = target.closest('.viewport-pan');
    if (viewportPan) {
      viewportPan.style.setProperty('--viewer-scale', scaleValue);
      viewportPan.style.setProperty('--viewer-base-width', `${baseWidth}px`);
      viewportPan.style.setProperty('--viewer-base-height', `${baseHeight}px`);
    }

    return clamped;
  }

  function updateResponsiveScale(target, { preserveManual = true } = {}) {
    if (!target) {
      return;
    }

    // Disable scaling on desktop completely
    if (window.innerWidth >= 1024) {
      applyScaleValue(target, 1);
      return 1;
    }

    const state = responsiveScaleState.get(target) || { manual: 1 };
    state.auto = computeAutoScale(target);
    state.min = Math.max(0.1, state.auto - 0.1);
    state.max = MAX_VIEWER_SCALE;
    if (!preserveManual) {
      state.manual = 1;
    }
    responsiveScaleState.set(target, state);
    const total = clampScale(state.auto * (state.manual || 1));
    applyScaleValue(target, total);
    const scroller = target.closest('.viewport-pan');
    if (scroller && !preserveManual) {
      scroller.scrollLeft = 0;
    }
    return total;
  }

  function scheduleGlobalScaleUpdate() {
    const targets = document.querySelectorAll('.orcamento');
    targets.forEach((target) => updateResponsiveScale(target));
  }
  function enhanceToolbar() {
    const toolbar = document.querySelector('.action-buttons');
    if (!toolbar || toolbar.dataset.enhanced === 'true') {
      return toolbar || null;
    }

    toolbar.dataset.enhanced = 'true';
    toolbar.querySelectorAll('.actions-inline-hint').forEach((node) => node.remove());
    document.body.classList.add('quotation-viewer');
    return toolbar;
  }

  function getPreferredRegionSymbol() {
    const REGION_SYMBOL_MAP = { BR: 'R$', UK: '£' };

    const safeGetLocalRegion = () => {
      try {
        return localStorage.getItem('user_region');
      } catch (error) {
        return null;
      }
    };

    const candidates = [
      safeGetLocalRegion(),
      document.documentElement?.getAttribute('data-region'),
      document.body?.getAttribute('data-server-region'),
    ];

    for (const region of candidates) {
      if (region && REGION_SYMBOL_MAP[region]) {
        return { region, symbol: REGION_SYMBOL_MAP[region] };
      }
    }

    return null;
  }

  function detectCurrentCurrencySymbol(root) {
    const SEARCH_ORDER = ['R$', '£'];
    const source = root || document.getElementById('quotationContainer') || document.querySelector('.orcamento');
    if (!source) {
      return null;
    }

    const textSnapshot = source.textContent || '';
    for (const candidate of SEARCH_ORDER) {
      if (textSnapshot.includes(candidate)) {
        return candidate;
      }
    }
    return null;
  }

  function replaceCurrencySymbol(target, fromSymbol, toSymbol) {
    if (!target || !fromSymbol || !toSymbol || fromSymbol === toSymbol) {
      return;
    }

    const escapeRegex = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const matcher = new RegExp(escapeRegex(fromSymbol), 'g');

    const walker = document.createTreeWalker(target, NodeFilter.SHOW_TEXT, null, false);
    const nodesToUpdate = [];
    while (walker.nextNode()) {
      const current = walker.currentNode;
      if (matcher.test(current.nodeValue)) {
        nodesToUpdate.push(current);
      }
    }

    nodesToUpdate.forEach((node) => {
      node.nodeValue = node.nodeValue.replace(matcher, toSymbol);
    });
  }

  function syncTemplateCurrencySymbol() {
    const preference = getPreferredRegionSymbol();
    if (!preference) {
      return;
    }

    const quotationRoot = document.getElementById('quotationContainer') || document.querySelector('.orcamento');
    if (!quotationRoot) {
      return;
    }

    const currentSymbol = detectCurrentCurrencySymbol(quotationRoot);
    if (!currentSymbol || currentSymbol === preference.symbol) {
      return;
    }

    const targets = [quotationRoot, document.querySelector('.action-buttons')].filter(Boolean);
    targets.forEach((target) => replaceCurrencySymbol(target, currentSymbol, preference.symbol));
  }

  function normalizeViewerStructure() {
    if (window.matchMedia('(min-width: 1024px)').matches) {
      document.querySelectorAll('.viewport-pan').forEach((pan) => {
        const parent = pan.parentNode;
        if (!parent) return;
        while (pan.firstChild) {
          parent.insertBefore(pan.firstChild, pan);
        }
        pan.remove();
      });
      return;
    }
    const quotation = document.getElementById('quotationContainer') || document.querySelector('.orcamento');
    if (!quotation) {
      return;
    }

    let templateShell = quotation.closest('.layout-shell:not(.layout-shell--actions):not(.layout-shell--hint)');
    if (!templateShell) {
      templateShell = document.createElement('div');
      templateShell.className = 'layout-shell';
      const parent = quotation.parentNode;
      if (parent) {
        parent.insertBefore(templateShell, quotation);
        templateShell.appendChild(quotation);
      }
    }

    const resolveViewportAnchor = () => templateShell.closest('.viewport-pan') || templateShell;

    const actionButtons = document.querySelector('.action-buttons');
    if (actionButtons) {
      let actionsShell = actionButtons.closest('.layout-shell--actions');
      if (!actionsShell) {
        actionsShell = document.createElement('div');
        actionsShell.className = 'layout-shell layout-shell--actions';
        const parent = actionButtons.parentNode;
        if (parent) {
          parent.insertBefore(actionsShell, actionButtons);
          actionsShell.appendChild(actionButtons);
        }
      }

      const anchor = resolveViewportAnchor();
      if (anchor?.parentNode && actionsShell.nextSibling !== anchor) {
        anchor.parentNode.insertBefore(actionsShell, anchor);
      }
    }

    let hintShell = document.querySelector('.layout-shell--hint');
    if (!hintShell) {
      hintShell = document.createElement('div');
      hintShell.className = 'layout-shell layout-shell--hint';
      const hint = document.createElement('div');
      hint.className = 'mobile-scroll-hint';
      hint.textContent = '👆 mexa na tela para ver o orçamento';
      hintShell.appendChild(hint);
    }

    const hintAnchor = resolveViewportAnchor();
    if (hintAnchor?.parentNode && hintShell.nextSibling !== hintAnchor) {
      hintAnchor.parentNode.insertBefore(hintShell, hintAnchor);
    }
  }

  function getViewportTarget() {
    return document.getElementById('quotationContainer') || document.querySelector('.viewport-pan') || document.querySelector('.orcamento');
  }

  function ensureViewportScroller() {
    if (window.matchMedia('(min-width: 1024px)').matches) {
      return;
    }
    const quotation = document.getElementById('quotationContainer') || document.querySelector('.orcamento');
    if (!quotation) {
      return;
    }

    const templateShell = quotation.closest('.layout-shell:not(.layout-shell--actions):not(.layout-shell--hint)') || quotation;

    let viewportPan = templateShell.closest('.viewport-pan');
    if (!viewportPan) {
      viewportPan = document.createElement('div');
      viewportPan.className = 'viewport-pan';

      const parent = templateShell.parentNode;
      if (parent) {
        parent.insertBefore(viewportPan, templateShell);
        viewportPan.appendChild(templateShell);
      }
    }

    viewportPan.style.touchAction = 'pan-x pan-y';
    viewportPan.style.overscrollBehaviorX = 'contain';
    viewportPan.style.WebkitOverflowScrolling = 'touch';

    setupViewerScrollbar(viewportPan);
  }

  let staticPreviewAttempts = 0;

  async function renderStaticPreviewImage() {
    if (window.matchMedia('(min-width: 1024px)').matches) {
      return;
    }
    const viewportPan = document.querySelector('.viewport-pan');
    const quotation = document.getElementById('quotationContainer') || document.querySelector('.orcamento');
    if (!viewportPan || !quotation || viewportPan.dataset.staticPreview === 'true') {
      return;
    }

    if (typeof window.html2canvas !== 'function') {
      if (staticPreviewAttempts < 10) {
        staticPreviewAttempts += 1;
        window.setTimeout(renderStaticPreviewImage, 200);
      }
      return;
    }

    try {
      const canvas = await window.html2canvas(quotation, {
        backgroundColor: '#ffffff',
        scale: Math.min(2, window.devicePixelRatio || 1.5),
        useCORS: true,
        logging: false,
      });

      const previewWrapper = document.createElement('div');
      previewWrapper.className = 'static-preview';

      const imageWrap = document.createElement('div');
      imageWrap.className = 'static-preview__image-wrap';

      const image = document.createElement('img');
      image.className = 'static-preview__image';
      image.src = canvas.toDataURL('image/png');
      image.alt = 'Prévia completa do orçamento';
      image.loading = 'lazy';
      imageWrap.appendChild(image);

      const download = document.createElement('button');
      download.type = 'button';
      download.className = 'static-preview__cta';
      download.textContent = 'Baixe o orçamento para ampliar';
      download.addEventListener('click', () => {
        if (typeof window.downloadImage === 'function') {
          window.downloadImage();
          return;
        }
        const fallbackName = (document.title || 'orcamento').trim().replace(/\s+/g, '-').toLowerCase();
        window.LuminaFlow?.downloadQuotationImage?.({ fileName: fallbackName });
      });

      previewWrapper.append(imageWrap, download);

      const layoutShell = quotation.closest('.layout-shell');
      if (layoutShell) {
        layoutShell.style.display = 'none';
        layoutShell.setAttribute('aria-hidden', 'true');
      } else {
        quotation.style.display = 'none';
        quotation.setAttribute('aria-hidden', 'true');
      }

      viewportPan.classList.add('static-preview-mode');
      viewportPan.dataset.staticPreview = 'true';
      viewportPan.appendChild(previewWrapper);

      const scrollbar = document.querySelector('.viewer-scrollbar');
      if (scrollbar) {
        scrollbar.classList.add('is-hidden');
      }
    } catch (error) {
      console.error('Erro ao gerar preview estático do orçamento', error);
    }
  }

  function setupViewerScrollbar(scrollTarget) {
    const existing = document.querySelector('.viewer-scrollbar');
    const target = scrollTarget || getViewportTarget();
    if (!target) {
      if (existing) existing.remove();
      return;
    }

    const scrollbar = existing || document.createElement('div');
    scrollbar.className = 'viewer-scrollbar is-hidden';

    if (!existing) {
      const track = document.createElement('div');
      track.className = 'viewer-scrollbar__track';

      const thumb = document.createElement('div');
      thumb.className = 'viewer-scrollbar__thumb';
      track.appendChild(thumb);
      scrollbar.appendChild(track);
      document.body.appendChild(scrollbar);
    }

    const track = scrollbar.querySelector('.viewer-scrollbar__track');
    const thumb = scrollbar.querySelector('.viewer-scrollbar__thumb');

    if (!track || !thumb) {
      return;
    }

    if (!track.__viewerDragBound) {
      let dragStart = null;
      let targetScrollWidth = 0;
      let targetClientWidth = 0;

      const handlePointerDown = (event) => {
        event.preventDefault();
        scrollbar.classList.add('is-dragging');
        dragStart = {
          x: event.clientX,
          scrollLeft: target.scrollLeft,
        };
        targetScrollWidth = target.scrollWidth;
        targetClientWidth = target.clientWidth;
        window.addEventListener('pointermove', handlePointerMove);
        window.addEventListener('pointerup', handlePointerUp, { once: true });
      };

      const handlePointerMove = (event) => {
        if (!dragStart) return;
        const trackWidth = track.clientWidth;
        const maxScrollable = targetScrollWidth - targetClientWidth;
        if (maxScrollable <= 0 || trackWidth <= 0) return;

        const delta = event.clientX - dragStart.x;
        const scrollDelta = (delta / trackWidth) * targetScrollWidth;
        target.scrollLeft = Math.min(
          Math.max(dragStart.scrollLeft + scrollDelta, 0),
          maxScrollable
        );
      };

      const handlePointerUp = () => {
        dragStart = null;
        scrollbar.classList.remove('is-dragging');
        window.removeEventListener('pointermove', handlePointerMove);
      };

      track.addEventListener('pointerdown', handlePointerDown);
      track.__viewerDragBound = true;
    }

    const sync = () => {
      const maxScrollable = target.scrollWidth - target.clientWidth;
      if (maxScrollable <= 0) {
        scrollbar.classList.add('is-hidden');
        return;
      }

      const ratio = target.clientWidth / target.scrollWidth;
      const widthPercent = Math.max(ratio * 100, 8);
      thumb.style.width = `${widthPercent}%`;

      const trackWidth = track.clientWidth - 2;
      const thumbWidthPx = (widthPercent / 100) * trackWidth;
      const maxTranslate = Math.max(trackWidth - thumbWidthPx, 0);
      const offsetRatio = target.scrollLeft / maxScrollable;
      const translatePx = offsetRatio * maxTranslate;
      thumb.style.transform = `translate3d(${translatePx}px, 0, 0)`;
      scrollbar.classList.remove('is-hidden');
    };

    const requestSync = () => {
      if (scrollbar.__rafPending) return;
      scrollbar.__rafPending = true;
      window.requestAnimationFrame(() => {
        scrollbar.__rafPending = false;
        sync();
      });
    };

    if (target.__viewerScrollHandler) {
      target.removeEventListener('scroll', target.__viewerScrollHandler);
    }
    target.__viewerScrollHandler = requestSync;
    target.addEventListener('scroll', requestSync, { passive: true });

    if (!scrollbar.__resizeHandler) {
      scrollbar.__resizeHandler = () => requestSync();
      window.addEventListener('resize', scrollbar.__resizeHandler);
    }

    if (!scrollbar.__orientationHandler) {
      scrollbar.__orientationHandler = () => requestSync();
      window.addEventListener('orientationchange', scrollbar.__orientationHandler);
    }

    if (scrollbar.__postSyncTimers) {
      scrollbar.__postSyncTimers.forEach((timerId) => clearTimeout(timerId));
    }

    const extraDelays = [80, 320, 900];
    scrollbar.__postSyncTimers = extraDelays.map((delay) => setTimeout(requestSync, delay));

    if (document.fonts && typeof document.fonts.ready?.then === 'function') {
      document.fonts.ready.then(requestSync).catch(() => {});
    }

    requestSync();
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

  const DEFAULT_EXPORT_WIDTH = 800;
  const DEFAULT_EXPORT_PADDING = 0;
  const DEFAULT_EXPORT_SCALE = 2;
  const DEFAULT_WINDOW_WIDTH = 1440;

  function resolveExportConfig(options = {}) {
    const source = options.source || document.getElementById('quotationContainer') || document.querySelector('.orcamento');
    if (!source) {
      throw new Error('Elemento do orçamento não encontrado para exportação.');
    }

    const dataset = source.dataset || {};
    const exportWidth = Number(options.exportWidth || dataset.exportWidth) || DEFAULT_EXPORT_WIDTH;
    const exportPadding = Number(options.exportPadding || dataset.exportPadding) || DEFAULT_EXPORT_PADDING;
    const scale = Number(options.scale || dataset.exportScale) || DEFAULT_EXPORT_SCALE;
    const windowWidth = Number(options.windowWidth || dataset.exportWindowWidth) || DEFAULT_WINDOW_WIDTH;

    const backgroundCandidate = options.backgroundColor || dataset.exportBackground;
    let backgroundColor = typeof backgroundCandidate === 'string' && backgroundCandidate.trim() !== ''
      ? backgroundCandidate
      : null;

    if (!backgroundColor) {
      const bodyStyles = window.getComputedStyle(document.body);
      backgroundColor = bodyStyles.getPropertyValue('--export-background')?.trim()
        || bodyStyles.backgroundColor
        || '#ffffff';
    }

    return {
      source,
      backgroundColor,
      exportWidth,
      exportPadding,
      scale,
      windowWidth,
    };
  }

  async function captureQuotationCanvas(options = {}) {
    if (typeof html2canvas !== 'function') {
      throw new Error('Biblioteca html2canvas não carregada. Verifique sua conexão.');
    }

    const config = resolveExportConfig(options);
    const exportHost = document.createElement('div');
    exportHost.className = 'quotation-export-host';
    exportHost.style.setProperty('--quotation-export-width', `${config.exportWidth}px`);
    exportHost.style.setProperty('--quotation-export-padding', `${config.exportPadding}px`);
    exportHost.style.setProperty('--quotation-export-background', config.backgroundColor);

    const exportWrapper = document.createElement('div');
    exportWrapper.className = 'quotation-export';

    const clone = config.source.cloneNode(true);
    if (clone.id) {
      clone.dataset.originalId = clone.id;
      clone.id = `${clone.id}-export`;
    }
    clone.classList.add('quotation-export__content');

    exportWrapper.appendChild(clone);
    exportHost.appendChild(exportWrapper);
    document.body.appendChild(exportHost);

    const bounding = exportWrapper.getBoundingClientRect();
    const captureWidth = Math.round(bounding.width || (config.exportWidth + config.exportPadding * 2));
    const captureHeight = Math.round(exportWrapper.scrollHeight || bounding.height || config.source.scrollHeight || 0);

    try {
      if (document.fonts && typeof document.fonts.ready?.then === 'function') {
        await document.fonts.ready;
      }

      return await html2canvas(exportWrapper, {
        backgroundColor: config.backgroundColor,
        scale: config.scale,
        useCORS: true,
        logging: false,
        windowWidth: Math.max(config.windowWidth, captureWidth),
        windowHeight: Math.max(captureHeight, window.innerHeight),
        width: captureWidth,
        height: captureHeight,
      });
    } finally {
      exportHost.remove();
    }
  }

  async function downloadQuotationImage(options = {}) {
    const { fileName = 'orcamento', ...captureOptions } = options;

    await withToolbarHidden(async () => {
      const canvas = await captureQuotationCanvas(captureOptions);
      const link = document.createElement('a');
      link.download = fileName.endsWith('.png') ? fileName : `${fileName}.png`;
      link.href = canvas.toDataURL('image/png');
      link.click();
    });
  }

  async function downloadQuotationPdf(options = {}) {
    const { jsPDF } = window.jspdf || {};
    if (typeof jsPDF !== 'function') {
      throw new Error('Biblioteca jsPDF não carregada. Verifique sua conexão.');
    }

    const {
      fileName = 'orcamento',
      pdfOrientation = 'p',
      pdfFormat = 'a4',
      ...captureOptions
    } = options;

    await withToolbarHidden(async () => {
      const canvas = await captureQuotationCanvas(captureOptions);
      const imgData = canvas.toDataURL('image/png');

      const pdf = new jsPDF(pdfOrientation, 'mm', pdfFormat);
      const imgProps = pdf.getImageProperties(imgData);
      const pdfWidth = pdf.internal.pageSize.getWidth();
      const pdfHeight = pdf.internal.pageSize.getHeight();
      const scale = Math.min(pdfWidth / imgProps.width, pdfHeight / imgProps.height);
      const renderWidth = imgProps.width * scale;
      const renderHeight = imgProps.height * scale;
      const marginX = (pdfWidth - renderWidth) / 2;
      const marginY = Math.max(0, (pdfHeight - renderHeight) / 2);

      pdf.addImage(imgData, 'PNG', marginX, marginY, renderWidth, renderHeight);
      pdf.save(fileName.endsWith('.pdf') ? fileName : `${fileName}.pdf`);
    });
  }

  window.LuminaFlow = window.LuminaFlow || {};
  window.LuminaFlow.enhanceQuotationToolbar = enhanceToolbar;
  window.LuminaFlow.withToolbarHidden = withToolbarHidden;
  window.LuminaFlow.ensureViewportScroller = ensureViewportScroller;
  window.LuminaFlow.captureQuotationCanvas = captureQuotationCanvas;
  window.LuminaFlow.downloadQuotationImage = downloadQuotationImage;
  window.LuminaFlow.downloadQuotationPdf = downloadQuotationPdf;
  window.LuminaFlow.resolveExportConfig = resolveExportConfig;

  document.addEventListener('DOMContentLoaded', () => {
    normalizeViewerStructure();
    enhanceToolbar();
    ensureViewportScroller();
    if (!window.matchMedia('(min-width: 1024px)').matches) {
      renderStaticPreviewImage();
    }
    syncTemplateCurrencySymbol();
  }, { once: true });
})();
