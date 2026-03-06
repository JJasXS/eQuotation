<?php
// getDraftOrders.php - Get all DRAFT orders for a specific chat
require_once 'db_helper.php';

header('Content-Type: application/json');

$chatid = $_GET['chatid'] ?? null;

if (!$chatid) {
    echo json_encode(['success' => false, 'error' => 'chatid required']);
    exit;
}

try {
    $dbh = getFirebirdConnection();
    
    // Get all DRAFT orders for this chat
    $stmt = $dbh->prepare('
        SELECT ORDERID, CHATID, CREATEDAT, STATUS 
        FROM ORDER_TPL 
        WHERE CHATID = ? AND STATUS = ?
        ORDER BY CREATEDAT DESC
    ');
    $stmt->execute([$chatid, 'DRAFT']);
    $orders = $stmt->fetchAll(PDO::FETCH_ASSOC);
    
    echo json_encode([
        'success' => true,
        'count' => count($orders),
        'data' => $orders
    ]);
    
} catch (Exception $e) {
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}
?>
