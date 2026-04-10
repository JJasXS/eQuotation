<?php
require_once 'db_helper.php';

header('Content-Type: application/json');

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    echo json_encode([
        'success' => false,
        'status' => 'error',
        'message' => 'POST method required'
    ]);
    exit;
}

function splitSqlStatements($sql)
{
    $withoutBlockComments = preg_replace('/\/\*.*?\*\//s', '', $sql);
    if ($withoutBlockComments === null) {
        return [];
    }

    $parts = explode(';', $withoutBlockComments);
    $statements = [];

    foreach ($parts as $part) {
        $trimmed = trim($part);
        if ($trimmed !== '') {
            $statements[] = $trimmed;
        }
    }

    return $statements;
}

$dbh = null;

try {
    $sqlPath = dirname(__DIR__) . DIRECTORY_SEPARATOR . 'sql' . DIRECTORY_SEPARATOR . 'pricing_priority_rule_firebird.sql';
    if (!file_exists($sqlPath)) {
        throw new Exception('SQL file not found: ' . $sqlPath);
    }

    $rawSql = file_get_contents($sqlPath);
    if ($rawSql === false) {
        throw new Exception('Failed to read SQL file: ' . $sqlPath);
    }

    $statements = splitSqlStatements($rawSql);
    $ignoreTokens = [
        'already exists',
        'name in use',
        'duplicate value',
        'violation of primary or unique key constraint',
        'unsuccessful metadata update'
    ];

    $dbh = getFirebirdConnection();
    $dbh->beginTransaction();

    $executed = 0;
    $ignored = 0;
    $failed = 0;
    $errors = [];

    foreach ($statements as $statement) {
        $normalized = strtoupper(trim(preg_replace('/\s+/', ' ', $statement)));

        if (strpos($normalized, 'SET SQL DIALECT') === 0) {
            continue;
        }

        if ($normalized === 'COMMIT') {
            continue;
        }

        try {
            $dbh->exec($statement);
            $executed++;
        } catch (Exception $e) {
            $message = strtolower($e->getMessage());
            $shouldIgnore = false;
            foreach ($ignoreTokens as $token) {
                if (strpos($message, $token) !== false) {
                    $shouldIgnore = true;
                    break;
                }
            }

            if ($shouldIgnore) {
                $ignored++;
                continue;
            }

            $failed++;
            $errors[] = $e->getMessage();
        }
    }

    $dbh->commit();

    echo json_encode([
        'success' => $failed === 0,
        'status' => $failed === 0 ? 'success' : 'warning',
        'message' => 'Pricing priority initialization completed',
        'executed' => $executed,
        'ignored' => $ignored,
        'failed' => $failed,
        'errors' => $errors,
    ]);
} catch (Exception $e) {
    if (isset($dbh) && $dbh instanceof PDO && $dbh->inTransaction()) {
        $dbh->rollBack();
    }

    echo json_encode([
        'success' => false,
        'status' => 'error',
        'message' => 'Pricing priority initialization failed',
        'error' => $e->getMessage(),
    ]);
} finally {
    $dbh = null;
}
?>
