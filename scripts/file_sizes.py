"""Quick size audit for admin pages + their static assets."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

GROUPS = {
    'Admin templates': list(ROOT.glob('templates/admin*.html')),
    'Shared components': list(ROOT.glob('templates/components/*.html')),
    'CSS': list(ROOT.glob('static/css/*.css')),
    'Admin JS': list(ROOT.glob('static/js/admin_*.js')),
}

for label, files in GROUPS.items():
    print(f'\n== {label} ==')
    rows = sorted(((p.stat().st_size, p.relative_to(ROOT)) for p in files if p.is_file()), reverse=True)
    total = sum(sz for sz, _ in rows)
    for sz, rel in rows:
        print(f'  {sz/1024:8.1f} KB  {rel}')
    print(f'  {"-"*40}\n  {total/1024:8.1f} KB total ({len(rows)} files)')
