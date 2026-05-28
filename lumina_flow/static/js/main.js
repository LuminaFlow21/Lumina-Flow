// ========================================
// LUMINA FLOW - MAIN JAVASCRIPT
// ========================================

// Global state
const LANGUAGE_STORAGE_KEY = 'user_region';
const REGION_CONFIG = {
    BR: { language: 'pt-BR', currency: 'R$' },
    UK: { language: 'en-GB', currency: '£' }
};

const LANGUAGE_UI_OPTIONS = {
    BR: { flag: '🇧🇷', name: 'Português' },
    UK: { flag: '🇬🇧', name: 'English' }
};

let currentLanguage = REGION_CONFIG.UK.language;
let currentRegion = 'UK';
let translations = {};

// Load translations from JSON file
async function loadTranslations() {
    try {
        const response = await fetch('/translations.json?v=' + Date.now() + Math.random()); // Aggressive cache bust
        translations = await response.json();
        console.log('[i18n] Translations loaded:', Object.keys(translations));
    } catch (error) {
        console.error('[i18n] Error loading translations:', error);
    }
}

async function persistRegionToServer(region) {
    try {
        await fetch('/set-region', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ region })
        });
    } catch (error) {
        console.error('[i18n] Error setting region on server:', error);
    }
}

// Initialize language and region from localStorage, server, or browser
async function initializeLanguage() {
    const body = document.body;
    const serverRegion = body ? body.getAttribute('data-server-region') : null;
    const savedRegion = localStorage.getItem(LANGUAGE_STORAGE_KEY);

    console.log('[i18n] Init - savedRegion:', savedRegion, '| serverRegion:', serverRegion);

    let resolvedRegion = currentRegion;

    if (savedRegion && REGION_CONFIG[savedRegion]) {
        resolvedRegion = savedRegion;
    } else if (serverRegion && REGION_CONFIG[serverRegion]) {
        resolvedRegion = serverRegion;
        localStorage.setItem(LANGUAGE_STORAGE_KEY, resolvedRegion);
    } else {
        const browserLang = navigator.language || navigator.userLanguage || 'en';
        resolvedRegion = browserLang.startsWith('pt') ? 'BR' : 'UK';
        localStorage.setItem(LANGUAGE_STORAGE_KEY, resolvedRegion);
    }

    currentRegion = resolvedRegion;
    currentLanguage = REGION_CONFIG[currentRegion].language;
    document.documentElement.setAttribute('data-region', currentRegion);
    syncGlobalState();
    updateCurrencyDisplays();

    const selectors = document.querySelectorAll('[data-language-selector]');
    selectors.forEach(selector => {
        selector.value = currentRegion;
    });

    if (serverRegion !== currentRegion) {
        persistRegionToServer(currentRegion);
    }

    return Boolean(savedRegion && REGION_CONFIG[savedRegion]);
}

// Get translation by key
function t(key) {
    const keys = key.split('.');
    let value = translations[currentLanguage];
    
    for (const k of keys) {
        if (value && value[k]) {
            value = value[k];
        } else {
            return key; // Return key if translation not found
        }
    }
    
    return value;
}

// Update all translatable elements
function updateTranslations() {
    console.log('[i18n] Updating translations for:', currentLanguage);
    const elements = document.querySelectorAll('[data-i18n]');
    console.log('[i18n] Found', elements.length, 'elements');

    let translated = 0;
    let missing = 0;

    elements.forEach(element => {
        const key = element.getAttribute('data-i18n');
        const translation = t(key);
        if (translation && translation !== key) {
            element.textContent = translation;
            translated++;
        } else {
            console.warn('[i18n] Missing translation:', key);
            missing++;
        }
    });

    console.log(`[i18n] Done: ${translated} translated, ${missing} missing`);
}

async function applyRegionChange(newRegion, { reload = true } = {}) {
    if (!REGION_CONFIG[newRegion]) {
        console.warn('[i18n] Invalid region:', newRegion);
        return;
    }

    const previous = localStorage.getItem(LANGUAGE_STORAGE_KEY);
    currentRegion = newRegion;
    currentLanguage = REGION_CONFIG[newRegion].language;
    document.documentElement.setAttribute('data-region', currentRegion);
    localStorage.setItem(LANGUAGE_STORAGE_KEY, newRegion);
    console.log('[i18n] Region updated to:', newRegion);

    const selectors = document.querySelectorAll('[data-language-selector]');
    selectors.forEach(selector => {
        selector.value = newRegion;
    });

    await persistRegionToServer(newRegion);

    updateCurrencyDisplays();
    updateTranslations();
    updatePricing();
    updatePlaceholderTranslations();
    updateDataLabels();
    initLanguageControlClicks();
    syncGlobalState();

    if (reload && previous !== newRegion) {
        setTimeout(() => window.location.reload(), 150);
    }
}

function handleLanguageSelectorChange(event) {
    applyRegionChange(event.target.value);
}

// Current billing period
let currentBilling = 'monthly';

// Update pricing based on region and billing
function updatePricing() {
    const priceElements = document.querySelectorAll('[data-price]');
    priceElements.forEach(element => {
        const regionKey = currentRegion === 'BR' ? 'br' : 'uk';
        const attrName = `data-price-${regionKey}-${currentBilling}`;
        const price = element.getAttribute(attrName);
        if (price) {
            element.textContent = price;
        }
    });
    
    // Update period label
    const periodElements = document.querySelectorAll('[data-period]');
    const periodKey = currentBilling === 'monthly' ? 'pricing.per_month' : 'pricing.per_year';
    periodElements.forEach(el => {
        const translation = t(periodKey);
        if (translation && translation !== periodKey) {
            el.textContent = translation;
        }
    });
    
    // Update checkout buttons
    const checkoutButtons = document.querySelectorAll('[data-checkout]');
    checkoutButtons.forEach(button => {
        const regionKey = currentRegion === 'BR' ? 'br' : 'uk';
        const attrName = `data-price-id-${regionKey}-${currentBilling}`;
        const priceId = button.getAttribute(attrName);
        if (priceId) {
            button.setAttribute('data-price-id', priceId);
        }
    });
}

// Handle billing toggle
function initBillingToggle() {
    const toggleBtns = document.querySelectorAll('.toggle-btn');
    toggleBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            toggleBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentBilling = btn.getAttribute('data-billing');
            updatePricing();
        });
    });
}

// Show language selection modal on first visit
function showLanguageModal() {
    const modal = document.getElementById('language-modal');
    if (!modal) return;

    modal.style.display = 'flex';

    const buttons = modal.querySelectorAll('[data-region]');
    buttons.forEach(btn => {
        btn.addEventListener('click', () => {
            const region = btn.getAttribute('data-region');
            modal.style.display = 'none';
            applyRegionChange(region);
        });
    });
}

function attachLanguageSelectors() {
    const selectors = document.querySelectorAll('[data-language-selector]');
    selectors.forEach(selector => {
        selector.removeEventListener('change', handleLanguageSelectorChange);
        selector.addEventListener('change', handleLanguageSelectorChange);
    });
}

function initLanguageControlClicks() {
    const controls = document.querySelectorAll('[data-language-control]');
    controls.forEach(control => {
        if (control.dataset.languageControlInit === 'true') return;

        const select = control.querySelector('[data-language-selector]');
        const dropdown = control.querySelector('[data-language-dropdown]');
        const nameEl = control.querySelector('[data-language-name]');
        if (!select || !dropdown) return;

        const setActiveRegion = (region) => {
            const data = LANGUAGE_UI_OPTIONS[region] || LANGUAGE_UI_OPTIONS.UK;
            select.value = region;
            nameEl.textContent = data.name;

            dropdown.querySelectorAll('.language-option').forEach(option => {
                const optionRegion = option.dataset.region;
                option.classList.toggle('active', optionRegion === region);
                const optionData = LANGUAGE_UI_OPTIONS[optionRegion];
                if (optionData) {
                    option.querySelector('.language-option-flag').textContent = optionData.flag;
                    option.querySelector('.language-option-label').textContent = optionData.name;
                }
            });
        };

        const closeDropdown = () => {
            control.classList.remove('open');
            dropdown.setAttribute('aria-hidden', 'true');
        };

        const openDropdown = () => {
            control.classList.add('open');
            dropdown.setAttribute('aria-hidden', 'false');
        };

        const handleRegionChange = (region) => {
            closeDropdown();
            if (select.value !== region) {
                const changeEvent = new Event('change', { bubbles: true });
                select.value = region;
                select.dispatchEvent(changeEvent);
            } else {
                setActiveRegion(region);
            }
        };

        dropdown.querySelectorAll('.language-option').forEach(option => {
            option.addEventListener('click', (event) => {
                event.stopPropagation();
                handleRegionChange(option.dataset.region);
            });
            option.addEventListener('keydown', (event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    handleRegionChange(option.dataset.region);
                }
            });
        });

        control.addEventListener('click', (event) => {
            if (control.classList.contains('open')) {
                if (!dropdown.contains(event.target)) {
                    closeDropdown();
                }
                return;
            }
            openDropdown();
        });

        document.addEventListener('click', (event) => {
            if (!control.contains(event.target)) {
                closeDropdown();
            }
        });

        control.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
                closeDropdown();
            }
        });

        setActiveRegion(select.value);
        dropdown.setAttribute('aria-hidden', 'true');
        control.dataset.languageControlInit = 'true';
    });
}

function attachLanguageToggles() {
    const toggles = document.querySelectorAll('[data-language-toggle]');
    toggles.forEach(toggle => {
        toggle.addEventListener('click', () => {
            const nextRegion = currentRegion === 'BR' ? 'UK' : 'BR';
            applyRegionChange(nextRegion);
        });
    });
}

function updateCurrencyDisplays() {
    const currency = REGION_CONFIG[currentRegion].currency;
    const elements = document.querySelectorAll('.currency-label');
    elements.forEach(el => {
        el.textContent = currency;
    });
}

function syncGlobalState() {
    window.LuminaFlow = window.LuminaFlow || {};
    window.LuminaFlow.t = t;
    window.LuminaFlow.updateTranslations = updateTranslations;
    window.LuminaFlow.updatePricing = updatePricing;
    window.LuminaFlow.updatePlaceholderTranslations = updatePlaceholderTranslations;
    window.LuminaFlow.updateDataLabels = updateDataLabels;
    window.LuminaFlow.updateCurrencyDisplays = updateCurrencyDisplays;
    window.LuminaFlow.applyRegionChange = applyRegionChange;
    window.LuminaFlow.loadTranslations = loadTranslations;
    window.LuminaFlow.currentLanguage = currentLanguage;
    window.LuminaFlow.currentRegion = currentRegion;
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', async () => {
    await loadTranslations();
    const hasSavedLanguage = await initializeLanguage();
    attachLanguageSelectors();
    initLanguageControlClicks();
    attachLanguageToggles();
    updateTranslations();
    updatePricing();
    updatePlaceholderTranslations();
    updateDataLabels();
    initBillingToggle();
    initWhatsAppDrag();

    if (!hasSavedLanguage) {
        showLanguageModal();
    }
});

// Update placeholder attributes on inputs
function updatePlaceholderTranslations() {
    const elements = document.querySelectorAll('[data-i18n-placeholder]');
    elements.forEach(element => {
        const key = element.getAttribute('data-i18n-placeholder');
        const translation = t(key);
        if (translation && translation !== key) {
            element.setAttribute('placeholder', translation);
        }
    });
}

function updateDataLabels() {
    const elements = document.querySelectorAll('[data-i18n-label]');
    elements.forEach(element => {
        const key = element.getAttribute('data-i18n-label');
        const translation = t(key);
        if (translation && translation !== key) {
            element.setAttribute('data-label', translation);
        }
    });
}

function initWhatsAppDrag() {
    const container = document.querySelector('[data-whatsapp-container]');
    const fab = container?.querySelector('.whatsapp-fab[data-no-drag]') || document.querySelector('.whatsapp-fab');
    const hideToggle = container?.querySelector('[data-whatsapp-hide]');
    const handleButton = container?.querySelector('[data-whatsapp-handle]');
    const STORAGE_KEY = 'whatsapp_hidden';

    if (container && hideToggle && handleButton) {
        const applyHiddenState = (hidden) => {
            container.classList.toggle('whatsapp--hidden', hidden);
            hideToggle.checked = hidden;
        };

        const savedHidden = localStorage.getItem(STORAGE_KEY) === 'true';
        applyHiddenState(savedHidden);

        hideToggle.addEventListener('change', () => {
            const hidden = hideToggle.checked;
            applyHiddenState(hidden);
            localStorage.setItem(STORAGE_KEY, hidden);
        });

        handleButton.addEventListener('click', () => {
            const hidden = !container.classList.contains('whatsapp--hidden');
            applyHiddenState(!hidden);
            localStorage.setItem(STORAGE_KEY, !hidden);
        });
    }

    if (!fab || !window.PointerEvent) {
        return;
    }

    let isDragging = false;
    let movedDuringDrag = false;
    let suppressClick = false;
    let offsetX = 0;
    let offsetY = 0;
    const POSITION_KEY = 'whatsapp_fab_position';

    const clamp = (value, min, max) => Math.min(Math.max(value, min), max);
    const isTouchPointer = (event) => !event.pointerType || event.pointerType === 'touch' || event.pointerType === 'pen';

    const loadSavedPosition = () => {
        try {
            const raw = localStorage.getItem(POSITION_KEY);
            if (!raw) return null;
            const saved = JSON.parse(raw);
            if (typeof saved.left === 'number' && typeof saved.top === 'number') {
                return saved;
            }
        } catch (error) {
            console.warn('[WhatsApp FAB] Failed to parse saved position', error);
        }
        return null;
    };

    const applyPosition = (left, top) => {
        fab.style.left = `${left}px`;
        fab.style.top = `${top}px`;
        fab.style.right = 'auto';
        fab.style.bottom = 'auto';
        fab.style.position = 'fixed';
    };

    const savedPosition = loadSavedPosition();
    if (savedPosition) {
        const minMargin = 12;
        const maxX = window.innerWidth - fab.offsetWidth - minMargin;
        const maxY = window.innerHeight - fab.offsetHeight - minMargin;
        const clampedLeft = clamp(savedPosition.left, minMargin, maxX);
        const clampedTop = clamp(savedPosition.top, minMargin, maxY);
        applyPosition(clampedLeft, clampedTop);
    } else {
        // Ensure the button keeps its default CSS position until the user drags it
        fab.style.left = '';
        fab.style.top = '';
        fab.style.right = '';
        fab.style.bottom = '';
        fab.style.position = '';
    }

    const startDrag = (event) => {
        if (!isTouchPointer(event)) return;

        const rect = fab.getBoundingClientRect();
        offsetX = event.clientX - rect.left;
        offsetY = event.clientY - rect.top;
        applyPosition(rect.left, rect.top);

        isDragging = true;
        movedDuringDrag = false;
        fab.classList.add('whatsapp-fab--hold');
        fab.setPointerCapture?.(event.pointerId);
    };

    const moveDrag = (event) => {
        if (!isDragging) return;
        // Only block default scrolling once we've actually moved
        if (event.cancelable) {
            event.preventDefault();
        }

        const minMargin = 12;
        const maxX = window.innerWidth - fab.offsetWidth - minMargin;
        const maxY = window.innerHeight - fab.offsetHeight - minMargin;
        const nextX = clamp(event.clientX - offsetX, minMargin, maxX);
        const nextY = clamp(event.clientY - offsetY, minMargin, maxY);

        fab.style.left = `${nextX}px`;
        fab.style.top = `${nextY}px`;
        fab.classList.add('whatsapp-fab--dragging');
        movedDuringDrag = true;
        suppressClick = true;
    };

    const endDrag = (event) => {
        if (!isDragging) return;
        isDragging = false;
        fab.classList.remove('whatsapp-fab--dragging', 'whatsapp-fab--hold');
        fab.releasePointerCapture?.(event.pointerId);

        if (movedDuringDrag) {
            try {
                const rect = fab.getBoundingClientRect();
                const data = { left: rect.left, top: rect.top };
                localStorage.setItem(POSITION_KEY, JSON.stringify(data));
            } catch (error) {
                console.warn('[WhatsApp FAB] Failed to persist position', error);
            }
            setTimeout(() => {
                suppressClick = false;
            }, 150);
        } else {
            suppressClick = false;
        }

        movedDuringDrag = false;
    };

    fab.addEventListener('pointerdown', startDrag);
    fab.addEventListener('pointermove', moveDrag);
    fab.addEventListener('pointerup', endDrag);
    fab.addEventListener('pointercancel', endDrag);
    fab.addEventListener('click', (event) => {
        if (suppressClick) {
            event.preventDefault();
            event.stopImmediatePropagation();
        }
    }, true);
}

// Export functions for use in other scripts
syncGlobalState();
