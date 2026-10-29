# eQuotation service restart (client)

Python loads `main.py` once. Copying files into `C:\Apps\eQuotation` does **not** apply until the service restarts.

## Deploy-time one-time grant (recommended)

Full client deploy (elevated) now:

1. Saves the user who launched the installer (`DOMAIN\user`) before UAC.
2. Installs/starts `ProAcc_eQuotation`.
3. Runs `grant-equotation-restart-rights.ps1` so that user can **start/stop** the service later **without Admin**.

Scripts that do this:

- `client-deploy-and-service.cmd`
- `DeployCommands\eQuotation\deploy-eQuotation-github.cmd`
- `DeployCommands\eQuotation\deploy-eQuotation-gitlab.cmd`

Standalone (if the machine was installed before this change):

```bat
C:\Apps\eQuotation\deploy\windows\grant-equotation-restart-rights.cmd
```

Click Yes on UAC **once**. After that, hotfixes should not need Admin.

## Hotfix (no Admin after grant)

1. Copy updated files to `C:\Apps\eQuotation`.
2. Run `restart-equotation.cmd` (tries non-admin first; elevates only if denied).
3. Smoke-check Approved View e-PR; log should show `source=local`.

## Dev workaround without touching NSSM

```bat
set FLASK_PORT=8881
cd /d C:\Apps\eQuotation
.venv\Scripts\python.exe main.py
```

Open `http://127.0.0.1:8881/admin/procurement`.
