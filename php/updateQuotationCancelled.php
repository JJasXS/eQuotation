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
    
    // Firebird BOOLEAN stored as 'True'/'False' strings (matching getAllQuotations.php expectations)
    $cancelledValue = $cancelled ? 'True' : 'False';
    error_log("[DEBUG] updateQuotationCancelled: Setting DOCKEY=$dockey to CANCELLED='$cancelledValue'");
    
    $stmt = $dbh->prepare('UPDATE SL_QT SET CANCELLED = ? WHERE DOCKEY = ?');
    $result = $stmt->execute([$cancelledValue, $dockey]);
    
    // IMPORTANT: Commit the transaction to save changes to Firebird
    $dbh->commit();
    
    error_log("[DEBUG] updateQuotationCancelled: Execute result=" . ($result ? 'true' : 'false'));
    
    // Verify the update worked
    $verifyStmt = $dbh->prepare('SELECT CANCELLED FROM SL_QT WHERE DOCKEY = ?');
    $verifyStmt->execute([$dockey]);
    $record = $verifyStmt->fetch(PDO::FETCH_ASSOC);
    error_log("[DEBUG] updateQuotationCancelled: After update, DOCKEY=$dockey has CANCELLED=" . $record['CANCELLED']);
    
    echo json_encode(['success' => true]);
} catch (Exception $e) {
    error_log("[ERROR] updateQuotationCancelled: " . $e->getMessage());
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}
