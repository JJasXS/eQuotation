<?php
// getAreaCodes.php - Return available area codes
header('Content-Type: application/json');
require_once 'db_helper.php';

if ($_SERVER['REQUEST_METHOD'] !== 'GET') {
    echo json_encode(['success' => false, 'error' => 'GET method required']);
    exit;
}

try {
    $dbh = getFirebirdConnection();

    $stmt = $dbh->prepare('SELECT CODE FROM AREA ORDER BY CODE');
    $stmt->execute();
    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);

    $codes = [];
    foreach ($rows as $row) {
        $code = isset($row['CODE']) ? trim((string)$row['CODE']) : '';
        $normalized = preg_replace('/[^A-Za-z0-9]/', '', $code);
        if ($code !== '' && strlen($normalized) >= 3) {
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
}
?>