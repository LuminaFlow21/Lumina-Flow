// ========================================
// LUMINA FLOW - MAIN JAVASCRIPT
// ========================================

// Global state
const LANGUAGE_STORAGE_KEY = 'user_region';
const REGION_CONFIG = {
    BR: { language: 'pt-BR', currency: 'R$' },
    UK: { language: 'en-GB', currency: '£' }
};

let currentLanguage = REGION_CONFIG.UK.language;
let currentRegion = 'UK';
let translations = {};

// Load translations from JSON file
async function loadTranslations() {
    try {
        const response = await fetch('/translations.json?v=' + Date.now()); // Cache bust
        translations = await response.json();
        console.log('[i18n] Translations loaded:', Object.keys(translations));
    } catch (error) {
        console.error('[i18n] Error loading translations:', error);
    }
}

// Initialize language and region from localStorage, server, or browser
async function initializeLanguage() {
    const body = document.body;
    const serverRegion = body ? body.getAttribute('data-server-region') : null;
    const savedRegion = localStorage.getItem(LANGUAGE_STORAGE_KEY);

    console.log('[i18n] Init - savedRegion:', savedRegion, '| serverRegion:', serverRegion);

    if (savedRegion && REGION_CONFIG[savedRegion]) {
        currentRegion = savedRegion;
    } else if (serverRegion && REGION_CONFIG[serverRegion]) {
        currentRegion = serverRegion;
    } else {
        const browserLang = navigator.language || navigator.userLanguage || 'en';
        currentRegion = browserLang.startsWith('pt') ? 'BR' : 'UK';
    }

    currentLanguage = REGION_CONFIG[currentRegion].language;
    document.documentElement.setAttribute('data-region', currentRegion);
    syncGlobalState();
    updateCurrencyDisplays();

    const selectors = document.querySelectorAll('[data-language-selector]');
    selectors.forEach(selector => {
        selector.value = currentRegion;
    });

    return Boolean(savedRegion);
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

    try {
        const response = await fetch('/set-region', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ region: newRegion })
        });
        await response.json();
    } catch (error) {
        console.error('[i18n] Error setting region on server:', error);
    }

    updateCurrencyDisplays();
    updateTranslations();
    updatePricing();
    updatePlaceholderTranslations();
    updateDataLabels();
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
    window.LuminaFlow.currentLanguage = currentLanguage;
    window.LuminaFlow.currentRegion = currentRegion;
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', async () => {
    await loadTranslations();
    const hasSavedLanguage = await initializeLanguage();
    attachLanguageSelectors();
    attachLanguageToggles();
    updateTranslations();
    updatePricing();
    updatePlaceholderTranslations();
    updateDataLabels();
    initBillingToggle();

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

// Export functions for use in other scripts
syncGlobalState();
