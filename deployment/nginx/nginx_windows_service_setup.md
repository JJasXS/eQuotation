# Running Nginx as a Windows Service (Auto-Start)

## Recommended: Use NSSM (Non-Sucking Service Manager)
NSSM is a free tool to run any program as a Windows service. This lets Nginx start automatically on boot, even if no user logs in.

### 1. Download NSSM
- Go to: https://nssm.cc/download
- Download the latest release (zip file)
- Extract to: `C:\nssm`

### 2. Install Nginx as a service
Open Command Prompt as Administrator and run:

```
C:\nssm\win64\nssm.exe install nginx
```

- In the dialog:
  - **Path**: `C:\nginx\nginx.exe`
  - **Startup directory**: `C:\nginx`
  - Click "Install service"

### 3. Start the service
```
net start nginx
```

### 4. Set service to auto-start (should be default)
```
sc config nginx start= auto
```

### 5. To stop or remove the service
```
net stop nginx
C:\nssm\win64\nssm.exe remove nginx confirm
```

---

## Alternative: Use Windows Task Scheduler (if you can't use NSSM)
- Create a new task to run `C:\nginx\nginx.exe` at system startup.
- Set to run with highest privileges.

---

## Notes
- If you update nginx.conf, reload with: `C:\nginx\nginx.exe -s reload`
- If you update Nginx, stop the service, replace files, then start again.
- Service will auto-restart if the server reboots or crashes.

---

For more, see: [docs/NGINX_REVERSE_PROXY_SETUP.md](../docs/NGINX_REVERSE_PROXY_SETUP.md)
