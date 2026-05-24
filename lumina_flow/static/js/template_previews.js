(function (window) {
  const LOADED_CLASS = 'is-loaded';
  const ERROR_CLASS = 'is-error';

  function markLoaded(frame) {
    const preview = frame.closest('.template-preview');
    if (preview) {
      preview.classList.add(LOADED_CLASS);
    }
  }

  function markError(frame, message) {
    const preview = frame.closest('.template-preview');
    if (!preview) return;
    preview.classList.add(ERROR_CLASS);
    const status = preview.querySelector('[data-preview-status]');
    if (status) {
      status.textContent = message || 'Não foi possível carregar a prévia.';
    }
  }

  function loadFrame(frame) {
    if (!frame || frame.hasAttribute('data-preview-loaded')) {
      return;
    }
    const src = frame.getAttribute('data-preview-src');
    if (!src) {
      return;
    }
    frame.addEventListener('load', () => {
      frame.setAttribute('data-preview-loaded', 'true');
      markLoaded(frame);
    }, { once: true });

    frame.addEventListener('error', () => {
      markError(frame);
    }, { once: true });

    frame.src = src;
  }

  function initTemplatePreviewFrames(root = document) {
    if (!root || typeof root.querySelectorAll !== 'function') {
      return;
    }

    const frames = root.querySelectorAll('iframe[data-preview-src]');
    if (!frames.length) {
      return;
    }

    if ('IntersectionObserver' in window) {
      const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            loadFrame(entry.target);
            observer.unobserve(entry.target);
          }
        });
      }, { rootMargin: '200px 0px' });

      frames.forEach((frame) => observer.observe(frame));
      return;
    }

    frames.forEach(loadFrame);
  }

  window.initTemplatePreviewFrames = initTemplatePreviewFrames;
})(window);
