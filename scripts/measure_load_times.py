"""Measure load times for the admin pages + static assets.

Usage: python scripts/measure_load_times.py
"""
import time
import urllib.request
import urllib.error

BASE = 'http://127.0.0.1:8880'
PATHS = [
    '/admin',
    '/admin/invoice-aging',
    '/admin/sales-cycle',
    '/admin/conversion-rate',
    '/login',
    '/static/css/admin.css',
    '/static/css/equotationIcyTheme.css',
    '/static/css/app_page_header.css',
    '/static/css/admin_report.css',
    '/static/js/admin_helpers.js',
    '/static/js/admin_invoice_aging.js',
    '/static/js/admin_sales_cycle.js',
    '/static/js/admin_conversion_rate.js',
]

REPEATS = 5
RETRIES = 3


def fetch(url):
    """Return (size, ms, status) or (None, None, error_message)."""
    last_err = None
    for attempt in range(RETRIES):
        try:
            start = time.perf_counter()
            req = urllib.request.Request(url, headers={
                'Cache-Control': 'no-cache',
                'Connection': 'close',
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
                return len(data), (time.perf_counter() - start) * 1000, str(resp.status)
        except urllib.error.HTTPError as e:
            return None, None, f'HTTP {e.code}'
        except Exception as e:
            last_err = f'ERR {type(e).__name__}'
            time.sleep(0.15)
    return None, None, last_err or 'ERR unknown'


print(f'Sampling {REPEATS}x per URL (with up to {RETRIES} retries).\n')
print(f'{"URL":<55} {"size KB":>8} {"min ms":>8} {"avg ms":>8} {"status":>10}')
print('-' * 94)

for path in PATHS:
    url = BASE + path
    samples = []
    size = 0
    status = '-'
    for _ in range(REPEATS):
        sz, ms, st = fetch(url)
        status = st
        if sz is not None:
            samples.append(ms)
            size = sz
        time.sleep(0.02)
    if samples:
        mn = min(samples)
        avg = sum(samples) / len(samples)
        print(f'{path:<55} {size/1024:>8.1f} {mn:>8.1f} {avg:>8.1f} {status:>10}')
    else:
        print(f'{path:<55} {"-":>8} {"-":>8} {"-":>8} {status:>10}')
