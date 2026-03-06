// Order Receipt JavaScript

document.addEventListener('DOMContentLoaded', function() {
    const printButton = document.querySelector('.print-button');
    const receiptContent = document.getElementById('receipt-content');
    const params = new URLSearchParams(window.location.search);
    const autoDownload = params.get('autodownload') === '1';
    const orderIdFromDom = receiptContent ? (receiptContent.dataset.orderid || 'unknown') : 'unknown';

    async function downloadReceiptPdf() {
        if (!receiptContent) {
            return;
        }

        const orderId = printButton ? (printButton.dataset.orderid || orderIdFromDom) : orderIdFromDom;
        const originalText = printButton ? printButton.textContent : '';
        const originalDisplay = printButton ? printButton.style.display : '';
        if (printButton) {
            printButton.disabled = true;
            printButton.textContent = 'Generating PDF...';
            printButton.style.display = 'none';
        }

        try {
            if (typeof html2pdf === 'undefined') {
                window.print();
                return;
            }

            const options = {
                margin: 8,
                filename: `order-receipt-${orderId}.pdf`,
                image: { type: 'jpeg', quality: 0.98 },
                html2canvas: { scale: 2, useCORS: true },
                jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' }
            };

            await html2pdf().set(options).from(receiptContent).save();
        } catch (error) {
            console.error('Failed to generate PDF:', error);
            window.print();
        } finally {
            if (printButton) {
                printButton.style.display = originalDisplay;
                printButton.disabled = false;
                printButton.textContent = originalText;
            }
        }
    }

    if (printButton) {
        printButton.addEventListener('click', downloadReceiptPdf);
    }

    if (autoDownload) {
        downloadReceiptPdf().finally(() => {
            if (window.opener) {
                setTimeout(() => {
                    window.close();
                }, 800);
            }
        });
    }
});
