<?php
// deleteDraftQuotation.php - Delete a draft from SL_QTDRAFT and SL_QTDTLDRAFT
header('Content-Type: application/json');
require_once 'db_helper.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    echo json_encode(['success' => false, 'error' => 'POST method required']);
    exit;
}

$data = json_decode(file_get_contents('php://input'), true);
$dockey = $data['dockey'] ?? null;

if (!$dockey || !is_numeric($dockey)) {
    echo json_encode(['success' => false, 'error' => 'Valid dockey required']);
    exit;
}

$dockey = (int)$dockey;

try {
    $dbh = getDbConnection();
    $dbh->beginTransaction();

    // Delete detail lines first (FK constraint)
    $stmtDtl = $dbh->prepare('DELETE FROM SL_QTDTLDRAFT WHERE DOCKEY = ?');
    $stmtDtl->execute([$dockey]);

    // Delete header row
    $stmtHdr = $dbh->prepare('DELETE FROM SL_QTDRAFT WHERE DOCKEY = ?');
    $stmtHdr->execute([$dockey]);

    $dbh->commit();

    echo json_encode(['success' => true, 'dockey' => $dockey]);
} catch (Exception $e) {
    if (isset($dbh) && $dbh->inTransaction()) {
        $dbh->rollBack();
    }
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}
