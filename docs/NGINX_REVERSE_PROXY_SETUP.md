# Nginx Reverse Proxy Setup (Single Public Port)

This setup lets clients access your app through one public port (typically `80`), while your services continue running internally:

- Flask: `127.0.0.1:5000`
- FastAPI: `127.0.0.1:8000`
- PHP/XAMPP: `127.0.0.1:8080`
Copy-Item "C:\Users\sqlsupport\eQuotation\deployment\nginx\nginx.windows.conf" "C:\nginx\conf\nginx.conf" -Force
## 1. Use the provided Nginx config

Config file in this repo:

- `deployment/nginx/equotation.conf`

It routes:

- `/` -> Flask (`5000`)
- `/auth/*`, `/api/*`, `/docs`, `/openapi.json` -> FastAPI (`8000`)
- `/php/*` -> PHP (`8080`)

## 2. Install Nginx on the server

### Windows (quick path)

1. Download Nginx for Windows from official nginx.org.
2. Extract to something like `C:\nginx`.
3. Copy `deployment/nginx/equotation.conf` into `C:\nginx\conf\conf.d\equotation.conf`.
4. Ensure `C:\nginx\conf\nginx.conf` includes:

```nginx
http {
    include       mime.types;
    default_type  application/octet-stream;

    include conf.d/*.conf;
}
```

5. Validate config:

```powershell
cd C:\nginx
.\nginx.exe -t
```

6. Start/reload:

```powershell
.\nginx.exe
# or reload after changes
.\nginx.exe -s reload
```

## 3. Keep backend services bound to localhost

For security, keep these internal-only:

- Flask on `127.0.0.1:5000`
- FastAPI on `127.0.0.1:8000`
- Apache/PHP on `127.0.0.1:8080`

Then only expose Nginx (`80` or `443`) publicly.

## 4. Update environment base URL

Your `.env` should use the public entrypoint of Nginx, for example:

```env
BASE_API_URL=http://localhost
```

On client production server, use host/domain, e.g.:

```env
BASE_API_URL=http://my-server-or-domain
```

Do **not** append port if using `80`/`443`.

## 5. Firewall rules

Open only:

- `80` (HTTP) and optionally `443` (HTTPS)

Keep `5000`, `8000`, `8080` closed from external access.

## 6. Health checks

From server:

```powershell
curl http://localhost/
curl http://localhost/auth/email-lookup -Method POST -Body '{"email":"admin@gmail.com"}' -ContentType 'application/json'
curl http://localhost/php/getAdminByEmail.php?email=admin@gmail.com
```

If all return expected responses, single-port reverse proxy is working.
