function getCookie(name) {
    const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
    return match ? decodeURIComponent(match[2]) : null;
}

function money(amount) {
    return Number(amount).toLocaleString('en-IN');
}

let selectedPackage = null;

function ensureCheckoutModal() {
    let overlay = document.getElementById('checkoutOverlay');
    if (overlay) return overlay;

    overlay = document.createElement('div');
    overlay.className = 'auth-overlay';
    overlay.id = 'checkoutOverlay';
    overlay.innerHTML = `
        <div class="auth-modal">
            <div class="auth-head">
                <h3>Subscribe to <span id="checkoutPlanName"></span></h3>
                <button class="auth-close" type="button" id="checkoutClose" aria-label="Close">&times;</button>
            </div>
            <form class="auth-form" id="checkoutForm" novalidate>
                <label class="auth-field">
                    <span>Full name</span>
                    <input type="text" name="name" placeholder="Your full name" autocomplete="name" required>
                </label>
                <div class="auth-field-row">
                    <label class="auth-field">
                        <span>Email</span>
                        <input type="email" name="email" placeholder="you@example.com" autocomplete="email" required>
                    </label>
                    <label class="auth-field">
                        <span>Contact number</span>
                        <input type="tel" name="contact" placeholder="Phone number" autocomplete="tel" required>
                    </label>
                </div>
                <p class="auth-field-error" id="checkoutError" style="display:none;"></p>
                <button class="btn btn-primary auth-submit" type="submit" id="checkoutSubmit">Pay &#8377;<span id="checkoutAmount"></span></button>
            </form>
        </div>
    `;
    document.body.appendChild(overlay);

    overlay.addEventListener('click', function (event) {
        if (event.target === overlay) closeCheckoutModal();
    });
    document.getElementById('checkoutClose').addEventListener('click', closeCheckoutModal);
    document.getElementById('checkoutForm').addEventListener('submit', handleCheckoutSubmit);

    return overlay;
}

function openCheckoutModal(pkg) {
    selectedPackage = pkg;
    const overlay = ensureCheckoutModal();
    document.getElementById('checkoutPlanName').textContent = pkg.name;
    document.getElementById('checkoutAmount').textContent = money(pkg.price_value);
    document.getElementById('checkoutError').style.display = 'none';
    overlay.classList.add('open');
}

function closeCheckoutModal() {
    const overlay = document.getElementById('checkoutOverlay');
    overlay?.classList.remove('open');
}

function showCheckoutError(message) {
    const errorEl = document.getElementById('checkoutError');
    errorEl.textContent = message;
    errorEl.style.display = 'block';
}

async function startCheckout(pkg, buyer, { onError, onDone } = {}) {
    const reportError = onError || function (message) { alert(message); };

    try {
        const response = await fetch('/api/payments/create-order/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken'),
            },
            body: JSON.stringify({
                package_id: pkg.id,
                name: buyer.name,
                email: buyer.email,
                contact: buyer.contact,
            }),
        });

        const order = await response.json();

        if (!response.ok) {
            reportError(order.error || 'Could not start checkout. Please try again.');
            if (onDone) onDone();
            return;
        }

        if (typeof Razorpay === 'undefined') {
            reportError('Payment gateway failed to load. Please check your connection.');
            if (onDone) onDone();
            return;
        }

        const rzp = new Razorpay({
            key: order.key,
            amount: order.amount,
            currency: order.currency,
            order_id: order.order_id,
            name: 'NextGen AI',
            description: order.package_name + ' plan',
            prefill: { name: buyer.name, email: buyer.email, contact: buyer.contact },
            theme: { color: '#2563EB' },
            handler: async function (paymentResponse) {
                try {
                    const verifyResponse = await fetch('/api/payments/verify/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCookie('csrftoken'),
                        },
                        body: JSON.stringify(paymentResponse),
                    });
                    const result = await verifyResponse.json();
                    if (verifyResponse.ok && result.status === 'success') {
                        closeCheckoutModal();
                        alert('Payment successful! Welcome to the ' + order.package_name + ' plan.');
                    } else {
                        reportError('Payment verification failed. Please contact support.');
                    }
                } finally {
                    if (onDone) onDone();
                }
            },
            modal: {
                ondismiss: function () {
                    if (onDone) onDone();
                },
            },
        });

        rzp.open();
    } catch (err) {
        reportError('Something went wrong. Please try again.');
        if (onDone) onDone();
    }
}

async function handleCheckoutSubmit(event) {
    event.preventDefault();
    if (!selectedPackage) return;

    const form = event.target;
    const submitBtn = document.getElementById('checkoutSubmit');
    const name = form.name.value.trim();
    const email = form.email.value.trim();
    const contact = form.contact.value.trim();

    if (!name || !email || !contact) {
        showCheckoutError('Please fill in all fields.');
        return;
    }

    submitBtn.disabled = true;
    startCheckout(selectedPackage, { name: name, email: email, contact: contact }, {
        onError: showCheckoutError,
        onDone: function () {
            submitBtn.disabled = false;
        },
    });
}

function handleBuyClick(pkg, button) {
    if (window.CURRENT_USER) {
        const originalText = button.textContent;
        button.disabled = true;
        button.textContent = 'Processing...';
        startCheckout(pkg, window.CURRENT_USER, {
            onDone: function () {
                button.disabled = false;
                button.textContent = originalText;
            },
        });
        return;
    }

    openCheckoutModal(pkg);
}

function renderPricingCard(pkg) {
    const featureItems = pkg.features.map(function (feature) {
        return `<li>${feature}</li>`;
    }).join('');

    const cardClass = 'pricing-card' + (pkg.is_recommended ? ' recommended' : '');
    const priceHtml = pkg.is_custom_price
        ? `<div class="price">Custom</div>`
        : `<div class="price">&#8377;${money(pkg.price_value)}</div>`;

    const ctaHtml = pkg.is_custom_price
        ? `<a class="btn" href="${pkg.cta_link}">${pkg.cta_text}</a>`
        : `<button type="button" class="btn ${pkg.is_recommended ? 'btn-primary' : ''} buy-btn" data-package-id="${pkg.id}">${pkg.cta_text}</button>`;

    return `
        <article class="${cardClass}">
            <span class="badge">${pkg.badge}</span>
            <h3>${pkg.name}</h3>
            ${priceHtml}
            <ul>${featureItems}</ul>
            ${ctaHtml}
        </article>
    `;
}

async function loadPackages() {
    const content = document.getElementById('content');
    if (!content) return;

    try {
        const response = await fetch('/api/packages/');
        const pkgs = await response.json();

        content.innerHTML = pkgs.map(renderPricingCard).join('');

        content.querySelectorAll('.buy-btn').forEach(function (button) {
            button.addEventListener('click', function () {
                const pkg = pkgs.find(function (p) { return String(p.id) === button.dataset.packageId; });
                if (pkg) handleBuyClick(pkg, button);
            });
        });
    } catch (err) {
        console.error('Failed to load packages', err);
    }
}

loadPackages();
