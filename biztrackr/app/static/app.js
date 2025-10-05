// Common JavaScript functionality for BizTrackr

// Format currency as GBP
function formatGBP(amount) {
    return new Intl.NumberFormat('en-GB', {
        style: 'currency',
        currency: 'GBP'
    }).format(amount);
}

// Format dates consistently
function formatDate(dateStr) {
    return new Date(dateStr).toLocaleDateString('en-GB');
}

// Add data-amount attributes for all currency cells
document.querySelectorAll('[data-amount]').forEach(el => {
    const amount = parseFloat(el.dataset.amount);
    if (!isNaN(amount)) {
        el.textContent = formatGBP(amount);
    }
});

// Add data-date attributes for all date cells
document.querySelectorAll('[data-date]').forEach(el => {
    const date = el.dataset.date;
    if (date) {
        el.textContent = formatDate(date);
    }
});