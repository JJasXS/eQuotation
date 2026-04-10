<?php
// completeOrder.php - Submit draft order for approval (DRAFT → PENDING)
require_once 'db_helper.php';

header('Content-Type: application/json');

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    echo json_encode(['success' => false, 'error' => 'POST method required']);
    exit;
}

$data = json_decode(file_get_contents('php://input'), true);
$orderid = $data['orderid'] ?? null;

if (!$orderid) {
    echo json_encode(['success' => false, 'error' => 'orderid required']);
    exit;
}

$dbh = null;

try {
    $dbh = getFirebirdConnection();
    $dbh->beginTransaction();
    
    // Check if order has items
    $stmt = $dbh->prepare('SELECT COUNT(*) as item_count FROM ORDER_TPLDTL WHERE ORDERID = ?');
    $stmt->execute([$orderid]);
    $result = $stmt->fetch(PDO::FETCH_ASSOC);
    
    // Handle Firebird uppercase column names
    $itemCount = $result['item_count'] ?? $result['ITEM_COUNT'] ?? 0;
    if ($itemCount == 0) {
        throw new Exception('Cannot complete order with no items');
    }
    
    // Update order status from DRAFT to PENDING (submit for approval)
    $stmt = $dbh->prepare('UPDATE ORDER_TPL SET STATUS = ? WHERE ORDERID = ?');
    $stmt->execute(['PENDING', $orderid]);
    
    // Get order totals
    $stmt = $dbh->prepare('
        SELECT SUM(TOTAL) as total, SUM(DISCOUNT) as discount 
        FROM ORDER_TPLDTL 
        WHERE ORDERID = ?
    ');
    $stmt->execute([$orderid]);
    $result = $stmt->fetch(PDO::FETCH_ASSOC);

    $dbh->commit();
    
    echo json_encode([
        'success' => true,
        'orderid' => $orderid,
        'status' => 'PENDING',
        'grandTotal' => $result['total'] - $result['discount'],
        'message' => "Order #$orderid submitted for approval"
    ]);
} catch (Exception $e) {
    if ($dbh instanceof PDO && $dbh->inTransaction()) {
        $dbh->rollBack();
    }
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
} finally {
    $dbh = null;
}
?>