<?php
// getOrderDetails.php - Fetch order and all line items
require_once 'db_helper.php';

header('Content-Type: application/json');

$orderid = $_GET['orderid'] ?? null;

if (!$orderid) {
    echo json_encode(['success' => false, 'error' => 'orderid required']);
    exit;
}

try {
    $dbh = getFirebirdConnection();
    
    // Get order header
    $stmt = $dbh->prepare('
        SELECT ORDERID, CHATID, OWNEREMAIL, CUSTOMERCODE, CREATEDAT, STATUS 
        FROM ORDER_TPL 
        WHERE ORDERID = ?
    ');
    $stmt->execute([$orderid]);
    $order = $stmt->fetch(PDO::FETCH_ASSOC);
    
    if (!$order) {
        echo json_encode(['success' => false, 'error' => 'Order not found']);
        exit;
    }
    
    // Get order details (items)
    $stmt = $dbh->prepare('
        SELECT ORDERDTLID, ORDERID, DESCRIPTION, QTY, UNITPRICE, DISCOUNT 
        FROM ORDER_TPLDTL 
        WHERE ORDERID = ? 
        ORDER BY ORDERDTLID ASC
    ');
    $stmt->execute([$orderid]);
    $items = $stmt->fetchAll(PDO::FETCH_ASSOC);
    
    // Format items with proper types
    $formattedItems = [];
    foreach ($items as $item) {
        $formattedItems[] = [
            'ORDERDTLID' => intval($item['ORDERDTLID']),
            'ORDERID' => intval($item['ORDERID']),
            'DESCRIPTION' => $item['DESCRIPTION'],
            'QTY' => intval($item['QTY']),
            'UNITPRICE' => floatval($item['UNITPRICE']),
            'DISCOUNT' => $item['DISCOUNT'] ? floatval($item['DISCOUNT']) : 0
        ];
    }
    
    // Combine order data with items
    $orderData = [
        'ORDERID' => intval($order['ORDERID']),
        'CHATID' => intval($order['CHATID']),
        'OWNEREMAIL' => $order['OWNEREMAIL'] ?? null,
        'CUSTOMERCODE' => $order['CUSTOMERCODE'] ?? null,
        'CREATEDAT' => $order['CREATEDAT'],
        'STATUS' => $order['STATUS'],
        'items' => $formattedItems
    ];
    
    echo json_encode([
        'success' => true,
        'data' => $orderData
    ]);
} catch (Exception $e) {
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}
?>

