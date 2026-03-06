<?php
// getAllOrders.php - Get all orders for a specific chat (any status)
require_once 'db_helper.php';

header('Content-Type: application/json');

$chatid = $_GET['chatid'] ?? null;
$status = $_GET['status'] ?? null; // Optional filter: DRAFT, COMPLETED, etc.

if (!$chatid) {
    echo json_encode(['success' => false, 'error' => 'chatid required']);
    exit;
}

try {
    $dbh = getFirebirdConnection();
    
    // Get orders with optional status filter
    if ($status) {
        $stmt = $dbh->prepare('
            SELECT ORDERID, CHATID, OWNEREMAIL, CUSTOMERCODE, CREATEDAT, STATUS 
            FROM ORDER_TPL 
            WHERE CHATID = ? AND STATUS = ?
            ORDER BY CREATEDAT DESC
        ');
        $stmt->execute([$chatid, $status]);
    } else {
        $stmt = $dbh->prepare('
            SELECT ORDERID, CHATID, OWNEREMAIL, CUSTOMERCODE, CREATEDAT, STATUS 
            FROM ORDER_TPL 
            WHERE CHATID = ?
            ORDER BY CREATEDAT DESC
        ');
        $stmt->execute([$chatid]);
    }
    
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
