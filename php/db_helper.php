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
        error_log("[DB CONNECTION] Firebird connection established");
        return $dbh;
    } catch (PDOException $e) {
        error_log("[DB CONNECTION ERROR] Failed to connect: " . $e->getMessage());
        throw $e;
    }
}
?>
