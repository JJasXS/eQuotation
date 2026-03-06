<?php
// insertOrderByManual.php - Create order directly from form without chat requirement
header('Content-Type: application/json');
require_once 'db_helper.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    echo json_encode(['success' => false, 'error' => 'POST method required']);
    exit;
}

$data = json_decode(file_get_contents('php://input'), true);
$ownerEmail = $data['ownerEmail'] ?? null;
$customerCode = $data['customerCode'] ?? null;
$orderName = $data['orderName'] ?? 'Manual Order';
$items = $data['items'] ?? [];

if (!$ownerEmail) {
    echo json_encode(['success' => false, 'error' => 'ownerEmail required']);
    exit;
}

if (!$customerCode) {
    echo json_encode(['success' => false, 'error' => 'customerCode required']);
    exit;
}

if (empty($items)) {
    echo json_encode(['success' => false, 'error' => 'At least one item is required']);
    exit;
}

try {
    $dbh = getFirebirdConnection();
    
    // Create or get special MANUAL chat (CHATID = 0 or a dedicated manual chat)
    // Check if manual orders chat exists (CHATID = -1 for manual orders)
    $chatCheckStmt = $dbh->prepare('SELECT CHATID FROM CHAT_TPL WHERE CHATID = ?');
    $chatCheckStmt->execute([0]);
    $manualChat = $chatCheckStmt->fetch(PDO::FETCH_ASSOC);
    
    $manualChatId = 0;
    if (!$manualChat) {
        // Create the dummy chat for manual orders
        $chatInsert = $dbh->prepare('
            INSERT INTO CHAT_TPL (CHATID, CHATNAME, CREATEDAT, LASTMESSAGE, OWNEREMAIL, CUSTOMERCODE) 
            VALUES (?, ?, ?, ?, ?, ?)
        ');
        $chatInsert->execute([0, 'MANUAL_ORDERS', date('Y-m-d H:i:s'), 'System chat for manual orders', 'system@manual', null]);
        $manualChatId = 0;
    }
    
    // Get next ORDERID
    $orderStmt = $dbh->prepare('SELECT COALESCE(MAX(ORDERID), 0) + 1 FROM ORDER_TPL');
    $orderStmt->execute();
    $orderid = $orderStmt->fetchColumn();
    
    $created_at = date('Y-m-d H:i:s');
    
    // Insert order header with manual chat ID
    $orderInsert = $dbh->prepare('
        INSERT INTO ORDER_TPL (ORDERID, CHATID, OWNEREMAIL, CUSTOMERCODE, CREATEDAT, STATUS, REMARK) 
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ');
    $orderInsert->execute([$orderid, $manualChatId, $ownerEmail, $customerCode, $created_at, 'PENDING', 'MANUAL']);
    
    // Insert order details
    foreach ($items as $idx => $item) {
        $product = $item['product'] ?? '';
        $qty = (float)($item['qty'] ?? 0);
        $price = (float)($item['price'] ?? 0);
        
        if (!$product || $qty <= 0) {
            echo json_encode(['success' => false, 'error' => "Invalid item at index $idx"]);
            exit;
        }
        
        $detailStmt = $dbh->prepare('SELECT COALESCE(MAX(ORDERDTLID), 0) + 1 FROM ORDER_TPLDTL');
        $detailStmt->execute();
        $orderdtlid = $detailStmt->fetchColumn();
        
        $detailInsert = $dbh->prepare('
            INSERT INTO ORDER_TPLDTL (ORDERDTLID, ORDERID, DESCRIPTION, QTY, UNITPRICE, DISCOUNT) 
            VALUES (?, ?, ?, ?, ?, ?)
        ');
        $detailInsert->execute([$orderdtlid, $orderid, $product, $qty, $price, 0]);
    }
    
    echo json_encode([
        'success' => true,
        'orderid' => $orderid,
        'message' => 'Order created successfully'
    ]);

} catch (Exception $e) {
    error_log("insertOrderByManual.php error: " . $e->getMessage());
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}
?>
