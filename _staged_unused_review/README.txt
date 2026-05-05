eQuotation — staged “likely unused” assets (review before delete)
================================================================

Generated from a static trace of:
  • Flask routes in main.py that call render_template / render_protected_template
  • Jinja {% include %} chain from those templates
  • Grep for /static/ references in templates and for stray script names

Nothing here was deleted — files were MOVED out of templates/ and static/ so the app
should behave the same if this folder stays ignored.

CONTENTS (why staged)
---------------------
• templates/signInGuest.html — route /signInGuest renders newSignInGuest.html only.
• templates/pages/userApproval.html — not included or rendered by any route found.
• templates/components/admin_hamburger_menu.html — never {% include %}'d (dead wrapper).
• static/js/signInGuest.js — only referenced by signInGuest.html (above).
• static/js/admin_hamburger_menu.js — no template or Python reference found.
• static/js/chat.js — no template references (chat.html is still routed but empty).

If you want these removed permanently, say yes in chat and we can delete this folder.

To restore: move files back to their original paths under templates/ and static/.
