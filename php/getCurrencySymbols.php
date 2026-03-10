<?php
// getCurrencySymbols.php - Return available currency symbols
header('Content-Type: application/json');
require_once 'db_helper.php';

if ($_SERVER['REQUEST_METHOD'] !== 'GET') {
    echo json_encode(['success' => false, 'error' => 'GET method required']);
    exit;
}

try {
    $dbh = getFirebirdConnection();

    $stmt = $dbh->prepare('SELECT CODE FROM CURRENCY ORDER BY CODE');
    $stmt->execute();
    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);

    $symbols = [];
    foreach ($rows as $row) {
        $symbol = isset($row['CODE']) ? trim((string)$row['CODE']) : '';
        if ($symbol !== '') {
            $symbols[] = $symbol;
        }
    }

    echo json_encode([
        'success' => true,
        'data' => $symbols
    ]);
} catch (Exception $e) {
    echo json_encode([
        'success' => false,
        'error' => $e->getMessage()
    ]);
}
?>