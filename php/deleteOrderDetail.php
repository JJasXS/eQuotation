<?php
// deleteOrderDetail.php - Remove line item from order
require_once 'db_helper.php';

header('Content-Type: application/json');

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    echo json_encode(['success' => false, 'error' => 'POST method required']);
    exit;
}

$data = json_decode(file_get_contents('php://input'), true);
$orderdtlid = $data['orderdtlid'] ?? null;

if (!$orderdtlid) {
    echo json_encode(['success' => false, 'error' => 'orderdtlid required']);
    exit;
}

try {
    $dbh = getFirebirdConnection();
    
    // Get description before deleting (for response message)
    $stmt = $dbh->prepare('SELECT DESCRIPTION FROM ORDER_TPLDTL WHERE ORDERDTLID = ?');
    $stmt->execute([$orderdtlid]);
    $result = $stmt->fetch(PDO::FETCH_ASSOC);
    $description = $result['DESCRIPTION'] ?? 'Item';
    
    // Delete order detail
    $stmt = $dbh->prepare('DELETE FROM ORDER_TPLDTL WHERE ORDERDTLID = ?');
    $stmt->execute([$orderdtlid]);
    
    echo json_encode([
        'success' => true,
        'message' => "Removed $description from order"
    ]);
} catch (Exception $e) {
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}
?>
