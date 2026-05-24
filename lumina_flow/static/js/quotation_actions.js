document.addEventListener('DOMContentLoaded', () => {
  const root = document.querySelector('.qa-actions');
  if (!root) {
    return;
  }

  const dropdown = root.querySelector('.qa-actions-dropdown');
  const toggle = root.querySelector('[data-qa-toggle]');
  const whatsappButtons = root.querySelectorAll('[data-action-trigger="whatsapp"]');

  const generatorName = root.dataset.generatorName || 'Lumina Flow';
  const quotationCode = root.dataset.quotationCode || '#000000';
  const totalValue = root.dataset.totalValue || '0.00';
  const currencySymbol = root.dataset.currencySymbol || 'R$';

  const closeDropdown = () => {
    if (!dropdown) return;
    dropdown.classList.remove('open');
    dropdown.setAttribute('aria-hidden', 'true');
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
      const url = window.location.href;
      const message = `Orçamento ${quotationCode} no valor de ${currencySymbol} ${totalValue}`;
      if (navigator.share) {
        navigator.share({ title: document.title, text: message, url }).catch(() => {});
        return;
      }
      navigator.clipboard?.writeText(url).then(() => {
        alert('Link copiado para a área de transferência.');
      }).catch(() => {
        alert('Copie o link manualmente: ' + url);
      });
    },
    whatsapp: () => {
      const url = window.location.href;
      const message = `Orçamento ${quotationCode} gerado por ${generatorName} no valor de ${currencySymbol} ${totalValue}. Veja: ${url}`;
      window.open(`https://wa.me/?text=${encodeURIComponent(message)}`, '_blank', 'noopener');
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
});
