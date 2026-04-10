<?php
// getCurrencySymbols.php - Return available currency codes
header('Content-Type: application/json');
require_once 'db_helper.php';

if ($_SERVER['REQUEST_METHOD'] !== 'GET') {
    echo json_encode(['success' => false, 'error' => 'GET method required']);
    exit;
}

$dbh = null;

try {
    $dbh = getFirebirdConnection();

    $stmt = $dbh->prepare('SELECT CODE FROM CURRENCY ORDER BY CODE');
    $stmt->execute();
    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);

    $codes = [];
    foreach ($rows as $row) {
        $code = isset($row['CODE']) ? trim((string)$row['CODE']) : '';
        if ($code !== '') {
            $codes[] = $code;
        }
    }

    echo json_encode([
        'success' => true,
        'data' => $codes
    ]);
} catch (Exception $e) {
    echo json_encode([
        'success' => false,
        'error' => $e->getMessage()
    ]);
} finally {
    $dbh = null;
}
?>