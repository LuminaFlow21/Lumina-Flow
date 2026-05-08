// ========================================
// LUMINA FLOW - MAIN JAVASCRIPT
// ========================================

// Global state
let currentLanguage = 'en-GB';
let currentRegion = 'UK';
let translations = {};

// Load translations from JSON file
async function loadTranslations() {
    try {
        const response = await fetch('/translations.json');
        translations = await response.json();
    } catch (error) {
        console.error('Error loading translations:', error);
    }
}

// Initialize language and region from localStorage, server, or browser
async function initializeLanguage() {
    const body = document.body;
    const serverRegion = body ? body.getAttribute('data-server-region') : null;
    const savedRegion = localStorage.getItem('user_region');

    if (savedRegion) {
        // User has already chosen a language - use localStorage (priority)
        currentRegion = savedRegion;
        currentLanguage = savedRegion === 'BR' ? 'pt-BR' : 'en-GB';

        // If server has different region, sync it
        if (serverRegion && serverRegion !== savedRegion) {
            try {
                await fetch('/set-region', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ region: savedRegion })
                });
            } catch (error) {
                console.error('Error syncing region to server:', error);
            }
        }
    } else if (serverRegion) {
        // No localStorage yet, but server has a region
        currentRegion = serverRegion;
        currentLanguage = serverRegion === 'BR' ? 'pt-BR' : 'en-GB';
        localStorage.setItem('user_region', serverRegion);
    } else {
        // First visit - detect browser language
        const browserLang = navigator.language || navigator.userLanguage;
        if (browserLang.startsWith('pt')) {
            currentRegion = 'BR';
            currentLanguage = 'pt-BR';
        } else {
            currentRegion = 'UK';
            currentLanguage = 'en-GB';
        }
    }

    // Update language selector
    const selector = document.getElementById('language-selector');
    if (selector) {
        selector.value = currentRegion;
    }
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
    const elements = document.querySelectorAll('[data-i18n]');
    elements.forEach(element => {
        const key = element.getAttribute('data-i18n');
        const translation = t(key);
        if (translation && translation !== key) {
            element.textContent = translation;
        }
    });
}

// Handle language/region change
async function handleLanguageChange(event) {
    const newRegion = event.target.value;
    currentRegion = newRegion;
    currentLanguage = newRegion === 'BR' ? 'pt-BR' : 'en-GB';

    // Save to localStorage
    localStorage.setItem('user_region', newRegion);

    // Update server-side session
    try {
        await fetch('/set-region', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ region: newRegion })
        });
    } catch (error) {
        console.error('Error setting region:', error);
    }

    // Update translations
    updateTranslations();

    // Reload page to apply changes
    window.location.reload();
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
        btn.addEventListener('click', async () => {
            const region = btn.getAttribute('data-region');
            currentRegion = region;
            currentLanguage = region === 'BR' ? 'pt-BR' : 'en-GB';
            localStorage.setItem('user_region', region);

            // Update server-side session
            try {
                await fetch('/set-region', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ region: region })
                });
            } catch (error) {
                console.error('Error setting region:', error);
            }

            const selector = document.getElementById('language-selector');
            if (selector) selector.value = region;

            updateTranslations();
            updatePricing();
            updatePlaceholderTranslations();
            modal.style.display = 'none';
        });
    });
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', async () => {
    await loadTranslations();
    await initializeLanguage();
    updateTranslations();
    updatePricing();
    updatePlaceholderTranslations();
    initBillingToggle();

    // Show modal if no language has been explicitly chosen before
    if (!localStorage.getItem('user_region')) {
        showLanguageModal();
    }

    // Attach event listener to language selector
    const languageSelector = document.getElementById('language-selector');
    if (languageSelector) {
        languageSelector.addEventListener('change', handleLanguageChange);
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

// Export functions for use in other scripts
window.LuminaFlow = {
    t,
    currentLanguage,
    currentRegion,
    updateTranslations,
    updatePricing,
    updatePlaceholderTranslations
};
