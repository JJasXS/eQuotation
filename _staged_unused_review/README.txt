eQuotation — staged assets & deletion candidates (review before delete)
========================================================================

Everything under this folder is EXCLUDED from production deploy
(`deploy/windows/copy-runtime-tree.cmd` skips `_staged_unused_review`).

When you are sure nothing here is needed, you may DELETE THIS ENTIRE FOLDER
from the repository (or leave it if you still want local QA / history).

CONTENTS
--------

1) Original “likely unused” UI/static (static trace)
   • templates/signInGuest.html — route uses newSignInGuest.html only.
   • templates/pages/userApproval.html — not wired from routes found.
   • templates/components/admin_hamburger_menu.html — dead wrapper.
   • static/js/signInGuest.js, admin_hamburger_menu.js, chat.js — see earlier notes.

2) tests/  (moved from repo root)
   • Pytest + manual scripts + Playwright spec.
   • Run from repo root:  pytest
   • Or:  python _staged_unused_review/tests/test_api.py  (see each file’s docstring).

3) _archive_unused/  (moved from repo root)
   • Old diagnostics, sample payloads, archived scripts.

To restore a moved file: put it back at its original path under templates/, static/, or repo root.

If you want these removed permanently from git, say yes and delete `_staged_unused_review`
after confirming CI/scripts do not depend on it.
