// ========================================
// LUMINA FLOW - STRIPE CLIENT
// ========================================

// Create checkout session and redirect to Stripe
async function createCheckoutSession(priceId) {
    try {
        const response = await fetch('/create-checkout-session', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                price_id: priceId,
                currency: window.LuminaFlow.currentRegion === 'BR' ? 'brl' : 'gbp'
            }),
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
            
            const priceId = button.getAttribute('data-price-id');
            if (!priceId) {
                console.error('No price ID found on button');
                return;
            }
            
            createCheckoutSession(priceId);
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
