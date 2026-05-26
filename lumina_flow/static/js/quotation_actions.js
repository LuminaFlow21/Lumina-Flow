document.addEventListener('DOMContentLoaded', () => {
  const root = document.querySelector('.qa-actions');
  if (!root) {
    return;
  }

  const dropdown = root.querySelector('.qa-actions-dropdown');
  const toggle = root.querySelector('[data-qa-toggle]');
  const whatsappButtons = root.querySelectorAll('[data-action-trigger="whatsapp"]');
  const shareModal = root.querySelector('[data-share-modal]');
  const shareInput = shareModal?.querySelector('[data-share-link]');
  const shareCopyBtn = shareModal?.querySelector('[data-share-copy]');
  const shareCloseEls = shareModal ? [...shareModal.querySelectorAll('[data-share-close]')] : [];
  const shareHint = shareModal?.querySelector('[data-share-feedback]');

  const generatorName = root.dataset.generatorName || 'Lumina Flow';
  const quotationCode = root.dataset.quotationCode || '#000000';
  const totalValue = root.dataset.totalValue || '0.00';
  const currencySymbol = root.dataset.currencySymbol || 'R$';
  const sharePath = root.dataset.sharePath || window.location.pathname;
  const shareUrl = new URL(sharePath, window.location.origin).href;
  const whatsappNumberRaw = root.dataset.whatsappNumber || '';
  const whatsappNumber = whatsappNumberRaw.replace(/[^0-9]/g, '');

  const closeDropdown = () => {
    if (!dropdown) return;
    dropdown.classList.remove('open');
    dropdown.setAttribute('aria-hidden', 'true');
  };

  const closeShareModal = () => {
    if (shareModal) {
      shareModal.hidden = true;
      if (shareHint) {
        shareHint.textContent = 'Clique em “Copiar link” para enviar o orçamento.';
      }
    }
  };

  const openShareModal = async () => {
    const canUseNativeShare = typeof navigator.share === 'function' && window.isSecureContext;

    if (canUseNativeShare) {
      try {
        await navigator.share({
          title: document.title,
          text: `Orçamento ${quotationCode} no valor de ${currencySymbol} ${totalValue}`,
          url: shareUrl,
        });
      } catch (error) {
        if (error?.name !== 'AbortError') {
          console.warn('navigator.share falhou, abrindo modal fallback', error);
          openShareFallback();
        }
      }
      return;
    }

    if (!window.isSecureContext) {
      alert('O compartilhamento nativo do navegador exige conexão segura (https). Abrindo opções manualmente.');
    }

    openShareFallback();
  };

  const openShareFallback = () => {
    if (!shareModal) {
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(shareUrl).then(() => {
          alert('Link copiado para a área de transferência.');
        }).catch(() => {
          alert('Copie o link manualmente: ' + shareUrl);
        });
      } else {
        alert('Copie o link manualmente: ' + shareUrl);
      }
      return;
    }

    if (shareInput) {
      shareInput.value = shareUrl;
      shareInput.focus();
      shareInput.select();
    }
    shareModal.hidden = false;
  };

  if (toggle && dropdown) {
    toggle.addEventListener('click', (event) => {
      event.preventDefault();
      dropdown.classList.toggle('open');
      dropdown.setAttribute('aria-hidden', dropdown.classList.contains('open') ? 'false' : 'true');
    });

    document.addEventListener('click', (event) => {
      const isToggle = event.target === toggle || toggle.contains(event.target);
      const isDropdown = dropdown.contains(event.target);
      if (!isToggle && !isDropdown) {
        closeDropdown();
      }
    });
  }

  const handlers = {
    edit: () => window.openEditModal?.(),
    image: () => window.downloadImage?.(),
    pdf: () => window.downloadPDF?.(),
    share: () => {
      openShareModal();
    },
    whatsapp: () => {
      const message = `Orçamento ${quotationCode} gerado por ${generatorName} no valor de ${currencySymbol} ${totalValue}. Veja: ${shareUrl}`;
      const encoded = encodeURIComponent(message);
      const baseUrl = whatsappNumber.length ? `https://wa.me/${whatsappNumber}` : 'https://wa.me/';
      window.open(`${baseUrl}?text=${encoded}`, '_blank', 'noopener');
    },
  };

  const triggerAction = (action) => {
    const fn = handlers[action];
    if (typeof fn === 'function') {
      fn();
    }
    if (window.innerWidth < 1024) {
      closeDropdown();
    }
  };

  root.querySelectorAll('[data-action-trigger]').forEach((button) => {
    button.addEventListener('click', (event) => {
      event.preventDefault();
      const action = button.getAttribute('data-action-trigger');
      triggerAction(action);
    });
  });

  whatsappButtons.forEach((button) => {
    button.setAttribute('title', `Enviar orçamento como ${generatorName}`);
  });

  const tryLegacyCopy = () => {
    try {
      const previousSelection = document.getSelection()?.rangeCount ? document.getSelection().getRangeAt(0) : null;
      shareInput.select();
      shareInput.setSelectionRange(0, shareInput.value.length);
      const successful = document.execCommand('copy');
      if (previousSelection) {
        document.getSelection().removeAllRanges();
        document.getSelection().addRange(previousSelection);
      }
      return successful;
    } catch (error) {
      return false;
    }
  };

  if (shareCopyBtn && shareInput) {
    shareCopyBtn.addEventListener('click', async () => {
      const textToCopy = shareInput.value;
      shareInput.select();
      shareInput.setSelectionRange(0, textToCopy.length);

      let copied = false;

      if (navigator.clipboard && window.isSecureContext) {
        try {
          await navigator.clipboard.writeText(textToCopy);
          copied = true;
        } catch (error) {
          copied = tryLegacyCopy();
        }
      } else {
        copied = tryLegacyCopy();
      }

      if (copied) {
        if (shareHint) {
          shareHint.textContent = 'Link copiado! Envie para o seu cliente.';
        }
      } else if (shareHint) {
        shareHint.textContent = 'Não foi possível copiar automaticamente. Selecione o texto e copie manualmente.';
      }
    });
  }

  if (shareModal) {
    shareCloseEls.forEach((element) => {
      element.addEventListener('click', () => {
        closeShareModal();
      });
    });

    shareModal.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        closeShareModal();
      }
    });
  }
});
