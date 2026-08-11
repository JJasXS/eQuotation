# -*- coding: utf-8 -*-
from pathlib import Path
import re

p = Path(r"C:\Users\sqlsupport\eQuotation\templates\precurement\precurement.html")
t = p.read_text(encoding="utf-8")

# Insert currency + text clean helpers before groupBulkTransferLines
helper = """
        function normalizeBulkTransferCurrency(value) {
            const text = String(value == null ? '' : value).trim().toUpperCase();
            if (!text || text === '----' || text === '-' || text === 'N/A' || text === 'NA' || text === 'NONE' || text === 'NULL') {
                return 'MYR';
            }
            return text;
        }

        function cleanBulkTransferDisplayText(value) {
            if (value == null) return '';
            let text = String(value).trim();
            if ((text.startsWith("b'") && text.endsWith("'")) || (text.startsWith('b"') && text.endsWith('"'))) {
                text = text.slice(2, -1);
            }
            return text;
        }

"""

if "function normalizeBulkTransferCurrency" not in t:
    anchor = "        function groupBulkTransferLines(lines) {"
    if anchor not in t:
        raise SystemExit("groupBulkTransferLines missing")
    t = t.replace(anchor, helper + anchor, 1)
    print("inserted normalize helpers")

# Fix grouping to normalize currency
t = t.replace(
    "const currencyCode = String(line.currencyCode || 'MYR').trim() || 'MYR';",
    "const currencyCode = normalizeBulkTransferCurrency(line.currencyCode);",
    1,
)

# Fix description cell
t = t.replace(
    "<td class=\"col-desc\">${escapeHtml(line.description || '-')}</td>",
    "<td class=\"col-desc\">${escapeHtml(cleanBulkTransferDisplayText(line.description) || '-')}</td>",
    1,
)

# Fix updateBulkTransferSummary button enable/text
old_summary = """        function updateBulkTransferSummary() {
            const summary = document.getElementById('bulk-transfer-summary');
            const btn = document.getElementById('bulk-transfer-submit-btn');
            const info = summarizeBulkTransferSelection();
            if (summary) {
                if (!info.lineCount) {
                    summary.textContent = 'No lines selected.';
                } else {
                    summary.textContent = `${info.lineCount} line(s) from ${info.prCount} PR(s), creating ${info.poCount} purchase order(s).`;
                }
            }
            if (btn) btn.disabled = !info.lineCount || bulkTransferSubmitting || document.body.classList.contains('procurement-hide-transfer');
        }"""

# may have blank lines - use regex
pat_summary = re.compile(
    r"function updateBulkTransferSummary\(\) \{.*?if \(btn\) btn\.disabled = !info\.lineCount \|\| bulkTransferSubmitting \|\| document\.body\.classList\.contains\('procurement-hide-transfer'\);\s*\}",
    re.S,
)
new_summary = """function updateBulkTransferSummary() {
            const summary = document.getElementById('bulk-transfer-summary');
            const btn = document.getElementById('bulk-transfer-submit-btn');
            const info = summarizeBulkTransferSelection();
            const eligibleCount = (getVisibleBulkTransferLines() || []).length;
            const transferCount = info.lineCount || eligibleCount;
            if (summary) {
                if (info.lineCount) {
                    summary.textContent = `${info.lineCount} line(s) selected from ${info.prCount} PR(s) → ${info.poCount} PO(s). Confirm before transfer.`;
                } else if (eligibleCount) {
                    summary.textContent = `No lines ticked — Transfer to PO will use all ${eligibleCount} eligible line(s). Confirmation required.`;
                } else {
                    summary.textContent = 'No eligible lines loaded.';
                }
            }
            if (btn) {
                btn.disabled = !transferCount || bulkTransferSubmitting || document.body.classList.contains('procurement-hide-transfer');
                btn.textContent = info.lineCount
                    ? `Transfer selected to PO (${info.lineCount})`
                    : (eligibleCount ? `Transfer all eligible to PO (${eligibleCount})` : 'Transfer to PO');
            }
        }"""
t2, n = pat_summary.subn(new_summary, t, count=1)
if n != 1:
    raise SystemExit(f"summary replace failed {n}")
t = t2
print("updated summary")

# Patch confirmBulkTransferToPo start to auto-use all eligible when none selected
old_confirm_start = """            if (bulkTransferSubmitting) return;
            const info = summarizeBulkTransferSelection();
            if (!info.lineCount) {
                alert('Select at least one line to transfer.');
                return;
            }"""
new_confirm_start = """            if (bulkTransferSubmitting) return;
            let info = summarizeBulkTransferSelection();
            if (!info.lineCount) {
                const eligible = getVisibleBulkTransferLines() || [];
                if (!eligible.length) {
                    alert('No eligible lines to transfer.');
                    return;
                }
                bulkTransferSelectAllVisible();
                info = summarizeBulkTransferSelection();
                if (!info.lineCount) {
                    alert('No eligible lines to transfer.');
                    return;
                }
            }"""
if old_confirm_start not in t:
    raise SystemExit("confirm start missing")
t = t.replace(old_confirm_start, new_confirm_start, 1)
print("updated confirm")

# Also normalize currency in confirm preview grouping
t = t.replace(
    "const key = `${row.supplierCode || ''}||${row.currencyCode || 'MYR'}`;",
    "const key = `${row.supplierCode || ''}||${normalizeBulkTransferCurrency(row.currencyCode)}`;",
    1,
)
t = t.replace(
    """                    previewGroups.set(key, {
                        supplierCode: row.supplierCode || '',
                        currencyCode: row.currencyCode || 'MYR',
                        prs: new Set(),
                        lines: 0,
                    });""",
    """                    previewGroups.set(key, {
                        supplierCode: row.supplierCode || '',
                        currencyCode: normalizeBulkTransferCurrency(row.currencyCode),
                        prs: new Set(),
                        lines: 0,
                    });""",
    1,
)

# Bump css cache lightly via html link even if css unchanged - or bump for hint
t = t.replace(
    "precurement.css?v=20260811_bulk_filter_popup1",
    "precurement.css?v=20260811_bulk_transfer_clarify1",
    1,
)

p.write_text(t, encoding="utf-8")
print("DONE")
