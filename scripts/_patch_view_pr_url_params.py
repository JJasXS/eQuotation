from pathlib import Path
import re

path = Path(r"c:\Users\sqlsupport\eQuotation\templates\precurement\precurement.html")
text = path.read_text(encoding="utf-8")

def sub_once(pattern: str, repl: str, label: str) -> None:
    global text
    new_text, n = re.subn(pattern, repl, text, count=1, flags=re.S)
    if n != 1:
        raise SystemExit(f"Failed patch: {label} (matches={n})")
    text = new_text

sub_once(
    r"(if \(viewSelectedHeaderId != null && Number\(viewSelectedHeaderId\) === id\) \{.*?renderFilteredViewPurchaseRequests\(\);)\s+(return;)",
    r"\1\n                if (!opts.fromUrl) {\n                    syncViewPrToUrl();\n                }\n\n                \2",
    "toggle-deselect",
)

sub_once(
    r"(if \(Array\.isArray\(record\.details\) && record\.details\.length\) \{.*?renderFilteredViewPurchaseRequests\(\);)\s+(return;)",
    r"\1\n                if (!opts.fromUrl) {\n                    syncViewPrToUrl();\n                }\n\n                \2",
    "cached-details",
)

sub_once(
    r"(viewLoadingDetailIds\.add\(id\);\s+renderFilteredViewPurchaseRequests\(\);)\s+(fetchViewPurchaseRequestDetail\(record\))",
    r"\1\n            if (!opts.fromUrl) {\n                syncViewPrToUrl();\n            }\n\n            \2",
    "loading-detail",
)

sub_once(
    r"(updateViewApprovalButtonState\(\);\s+renderFilteredViewPurchaseRequests\(\);)\s+(syncViewPrLoadMoreUi\(\);)",
    r"\1\n            selectViewPrFromUrlIfPresent();\n\n            \2",
    "after-first-page-load",
)

path.write_text(text, encoding="utf-8")
print("Patched procurement.html")
