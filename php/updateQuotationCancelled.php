<?php
// updateQuotationCancelled.php - Toggle CANCELLED status for a quotation
header('Content-Type: application/json');
require_once 'db_helper.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    echo json_encode(['success' => false, 'error' => 'POST method required']);
    exit;
}

$data = json_decode(file_get_contents('php://input'), true);
$dockey = $data['dockey'] ?? null;
$cancelled = $data['cancelled'] ?? null;

if (!$dockey || !isset($cancelled)) {
    echo json_encode(['success' => false, 'error' => 'dockey and cancelled required']);
    exit;
}

try {
    $dbh = getFirebirdConnection();
    $stmt = $dbh->prepare('UPDATE SL_QT SET CANCELLED = ? WHERE DOCKEY = ?');
    $stmt->execute([$cancelled ? 1 : 0, $dockey]);
    echo json_encode(['success' => true]);
} catch (Exception $e) {
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}
