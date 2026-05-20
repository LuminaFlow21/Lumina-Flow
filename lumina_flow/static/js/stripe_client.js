// ========================================
// LUMINA FLOW - STRIPE CLIENT
// ========================================

// Create checkout session and redirect to Stripe
async function createCheckoutSession(options) {
    const payload = {};

    if (typeof options === 'string') {
        payload.price_id = options;
    } else if (options && typeof options === 'object') {
        if (options.priceId) {
            payload.price_id = options.priceId;
        }
        if (options.priceKey) {
            payload.priceIdKey = options.priceKey;
        }
        if (options.currency) {
            payload.currency = options.currency;
        }
    }

    if (!payload.price_id && !payload.priceIdKey) {
        console.error('No price identifier provided for checkout session');
        alert('Não foi possível iniciar o checkout. Tente novamente.');
        return;
    }

    if (!payload.currency) {
        payload.currency = (window.LuminaFlow?.currentRegion === 'BR') ? 'brl' : 'gbp';
    }

    try {
        const response = await fetch('/create-checkout-session', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload),
        });
        
        const data = await response.json();
        
        if (data.error) {
            console.error('Error creating checkout session:', data.error);
            alert(data.error);
            return;
        }
        
        // Redirect to Stripe Checkout
        if (data.checkout_url) {
            window.location.href = data.checkout_url;
        }
    } catch (error) {
        console.error('Error:', error);
        alert('An error occurred. Please try again.');
    }
}

// Handle checkout button clicks
function initCheckoutButtons() {
    const checkoutButtons = document.querySelectorAll('[data-checkout]');
    checkoutButtons.forEach(button => {
        button.addEventListener('click', (event) => {
            event.preventDefault();
            
            const region = window.LuminaFlow?.currentRegion === 'BR' ? 'br' : 'uk';
            const priceKey = button.getAttribute(`data-price-key-${region}`);
            const priceId = button.getAttribute('data-price-id');

            if (!priceId && !priceKey) {
                console.error('No price configuration found on button');
                alert('Configuração de preço indisponível. Tente novamente.');
                return;
            }

            createCheckoutSession({
                priceId,
                priceKey,
                currency: window.LuminaFlow?.currentRegion === 'BR' ? 'brl' : 'gbp'
            });
        });
    });
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    initCheckoutButtons();
});

// Export for use in other scripts
window.StripeClient = {
    createCheckoutSession,
    initCheckoutButtons
};
