<?php
// db_helper.php - Firebird DB connection helper

function loadEnvFile($envPath) {
    $env = [];

    if (!file_exists($envPath)) {
        return $env;
    }

    $lines = file($envPath, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
    if ($lines === false) {
        return $env;
    }

    foreach ($lines as $line) {
        $line = trim($line);
        if ($line === '' || $line[0] === '#') {
            continue;
        }

        $pos = strpos($line, '=');
        if ($pos === false) {
            continue;
        }

        $key = trim(substr($line, 0, $pos));
        $value = trim(substr($line, $pos + 1));

        // Remove optional surrounding quotes
        if ((strlen($value) >= 2) &&
            (($value[0] === '"' && $value[strlen($value) - 1] === '"') ||
             ($value[0] === "'" && $value[strlen($value) - 1] === "'"))) {
            $value = substr($value, 1, -1);
        }

        $env[$key] = $value;
    }

    return $env;
}

function findEnvFile() {
    $candidates = [];

    // Walk up from this file directory
    $dir = __DIR__;
    for ($i = 0; $i < 6; $i++) {
        $candidates[] = $dir . DIRECTORY_SEPARATOR . '.env';
        $parent = dirname($dir);
        if ($parent === $dir) {
            break;
        }
        $dir = $parent;
    }

    // Add current working directory and entry script locations
    $cwd = getcwd();
    if ($cwd) {
        $candidates[] = $cwd . DIRECTORY_SEPARATOR . '.env';
    }

    if (!empty($_SERVER['SCRIPT_FILENAME'])) {
        $scriptDir = dirname($_SERVER['SCRIPT_FILENAME']);
        $candidates[] = $scriptDir . DIRECTORY_SEPARATOR . '.env';
        $candidates[] = dirname($scriptDir) . DIRECTORY_SEPARATOR . '.env';
    }

    // Common Windows fallback paths when PHP is served from XAMPP but project lives elsewhere.
    $username = getenv('USERNAME') ?: '';
    if ($username !== '') {
        $candidates[] = 'C:' . DIRECTORY_SEPARATOR . 'Users' . DIRECTORY_SEPARATOR . $username . DIRECTORY_SEPARATOR . 'Chatbot' . DIRECTORY_SEPARATOR . '.env';
    }
    $candidates[] = 'C:' . DIRECTORY_SEPARATOR . 'Users' . DIRECTORY_SEPARATOR . 'Administrator' . DIRECTORY_SEPARATOR . 'Chatbot' . DIRECTORY_SEPARATOR . '.env';
    $candidates[] = dirname(__DIR__) . DIRECTORY_SEPARATOR . 'Chatbot' . DIRECTORY_SEPARATOR . '.env';

    // Return first existing .env
    foreach ($candidates as $candidate) {
        if (is_string($candidate) && file_exists($candidate)) {
            return $candidate;
        }
    }

    return null;
}

function getFirebirdConnection() {
    $envPath = findEnvFile();
    $env = $envPath ? loadEnvFile($envPath) : [];

    $host = isset($env['DB_HOST']) ? trim($env['DB_HOST']) : trim(getenv('DB_HOST') ?: 'localhost');
    $db = isset($env['DB_PATH']) ? $env['DB_PATH'] : (getenv('DB_PATH') ?: '');
    $user = isset($env['DB_USER']) ? $env['DB_USER'] : (getenv('DB_USER') ?: 'sysdba');
    $pass = isset($env['DB_PASSWORD']) ? $env['DB_PASSWORD'] : (getenv('DB_PASSWORD') ?: 'masterkey');

    if ($db === '') {
        throw new Exception('DB_PATH is not set in .env');
    }

    try {
        $dbh = new PDO("firebird:dbname=$db;host=$host", $user, $pass);
        $dbh->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
        $dbh->setAttribute(PDO::ATTR_DEFAULT_FETCH_MODE, PDO::FETCH_ASSOC);
        // Firebird PDO does not expose MYSQL-style charset DSN options; this keeps UTF-8 handling explicit.
        $dbh->exec("SET NAMES UTF8");
        error_log("[DB CONNECTION] Firebird connection established");
        return $dbh;
    } catch (PDOException $e) {
        error_log("[DB CONNECTION ERROR] Failed to connect: " . $e->getMessage());
        throw $e;
    }
}

function jsonResponse(int $statusCode, bool $success, string $message, $data = null, ?string $error = null): void {
    http_response_code($statusCode);
    echo json_encode([
        'success' => $success,
        'message' => $message,
        'data' => $data,
        'error' => $error,
    ]);
}

function badRequest(string $message, $data = null): void {
    jsonResponse(400, false, $message, $data, $message);
}

function notFound(string $message, $data = null): void {
    jsonResponse(404, false, $message, $data, $message);
}

function conflictResponse(string $message, $data = null): void {
    jsonResponse(409, false, $message, $data, $message);
}

function serverError(string $message, $data = null): void {
    jsonResponse(500, false, $message, $data, $message);
}

function nextSequenceValue(PDO $dbh, string $sequenceName): int {
    // Never use MAX(id)+1 for concurrent inserts; two sessions can pick the same key before commit.
    if (!preg_match('/^[A-Z0-9_]+$/', $sequenceName)) {
        throw new RuntimeException('Invalid sequence name: ' . $sequenceName);
    }

    try {
        $stmt = $dbh->query('SELECT NEXT VALUE FOR ' . $sequenceName . ' AS ID FROM RDB$DATABASE');
        $value = $stmt->fetchColumn();
        if ($value !== false && $value !== null) {
            return (int)$value;
        }
    } catch (Throwable $ignored) {
        // Fall through to GEN_ID syntax for older server compatibility.
    }

    try {
        $stmt = $dbh->query('SELECT GEN_ID(' . $sequenceName . ', 1) AS ID FROM RDB$DATABASE');
        $value = $stmt->fetchColumn();
        if ($value !== false && $value !== null) {
            return (int)$value;
        }
    } catch (Throwable $ignored) {
        // Re-thrown below with actionable context.
    }

    throw new RuntimeException(
        'Required Firebird sequence is missing or inaccessible: ' . $sequenceName .
        '. Create the sequence and grant usage before enabling this endpoint.'
    , 409);
}

function appSequenceName(string $logicalKey): string {
    $map = [
        'CHAT_MESSAGE_ID' => 'SEQ_CHAT_TPLDTL_MESSAGEID',
        'ORDER_ID' => 'SEQ_ORDER_TPL_ORDERID',
        'ORDER_DETAIL_ID' => 'SEQ_ORDER_TPLDTL_ORDERDTLID',
    ];

    if (!isset($map[$logicalKey])) {
        throw new RuntimeException('Unknown logical sequence key: ' . $logicalKey);
    }

    return $map[$logicalKey];
}

function nextAppId(PDO $dbh, string $logicalKey): int {
    return nextSequenceValue($dbh, appSequenceName($logicalKey));
}

function rejectUnsafeSharedInsert(string $context, array $tables): void {
    $tableList = implode(', ', $tables);
    throw new RuntimeException(
        $context . ' is disabled for direct DB insert because key generation for shared SQL Account tables (' .
        $tableList . ') cannot safely use MAX+1 under concurrency. Use vendor-supported SDK/COM/API flow.',
        409
    );
}

// Backward-compatible alias used by older endpoints.
function getDbConnection() {
    return getFirebirdConnection();
}
?>
