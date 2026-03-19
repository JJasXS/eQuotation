# SOLUTION: Enable Firebird Extension in XAMPP

## Problem
PHP error: `Call to undefined function ibase_prepare()`

This means the PHP Firebird/InterBase extension is not enabled.

## Solution

### Step 1: Enable InterBase Extension in php.ini

1. Open XAMPP Control Panel
2. Click "Config" button next to Apache
3. Select "PHP (php.ini)"
4. Find this line (around line 900-950):
   ```
   ;extension=interbase
   ```
5. Remove the semicolon to uncomment it:
   ```
   extension=interbase
   ```
6. Save the file

### Step 2: Verify the Extension Files Exist

Check if these files exist:
- `C:\xampp\php\ext\php_interbase.dll`
- `C:\xampp\php\gds32.dll`

If `php_interbase.dll` is missing:
1. Download PHP InterBase extension for your PHP version
2. Copy to `C:\xampp\php\ext\`

If `gds32.dll` is missing:
1. Download Firebird client library
2. Copy `gds32.dll` or `fbclient.dll` to:
   - `C:\xampp\php\`
   - `C:\Windows\System32\`

### Step 3: Restart Apache

1. In XAMPP Control Panel, click "Stop" for Apache
2. Wait a few seconds
3. Click "Start" for Apache

### Step 4: Verify Installation

Run this test:
```bash
python test_php_extensions.py
```

## Alternative Solution (if extension is not available)

If the InterBase extension is not available for your PHP version, you may need to:
1. Downgrade PHP to version 7.x (InterBase is better supported)
2. Or use a different PHP installation that includes Firebird support
3. Or use PDO_Firebird extension instead (requires code changes)

## Quick Test

After enabling the extension, run:
```bash
python test_request_change.py
```

The response should now be valid JSON instead of a Fatal Error.
