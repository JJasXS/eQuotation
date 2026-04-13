<?php
// insertOrderByManual.php - Create order directly from form without chat requirement
header('Content-Type: application/json');
require_once 'db_helper.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    badRequest('POST method required');
    exit;
}

$data = json_decode(file_get_contents('php://input'), true);
$ownerEmail = $data['ownerEmail'] ?? null;
$customerCode = $data['customerCode'] ?? null;
$orderName = $data['orderName'] ?? 'Manual Order';
$items = $data['items'] ?? [];

if (!$ownerEmail) {
    badRequest('ownerEmail required');
    exit;
}

if (!$customerCode) {
    badRequest('customerCode required');
    exit;
}

if (empty($items)) {
    badRequest('At least one item is required');
    exit;
}

$dbh = null;

try {
    $dbh = getFirebirdConnection();
    $dbh->beginTransaction();
    
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
    
    // MAX+1 is unsafe under concurrency; use a sequence so concurrent sessions cannot collide.
    $orderid = nextAppId($dbh, 'ORDER_ID');
    
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
            throw new Exception("Invalid item at index $idx");
        }
        
        $orderdtlid = nextAppId($dbh, 'ORDER_DETAIL_ID');
        
        $detailInsert = $dbh->prepare('
            INSERT INTO ORDER_TPLDTL (ORDERDTLID, ORDERID, DESCRIPTION, QTY, UNITPRICE, DISCOUNT) 
            VALUES (?, ?, ?, ?, ?, ?)
        ');
        $detailInsert->execute([$orderdtlid, $orderid, $product, $qty, $price, 0]);
        if ($detailInsert->rowCount() === 0) {
            throw new RuntimeException('No detail row inserted', 409);
        }
    }

    $dbh->commit();
    
    jsonResponse(201, true, 'Order created successfully', ['orderid' => (int)$orderid], null);

} catch (RuntimeException $e) {
    if ($dbh instanceof PDO && $dbh->inTransaction()) {
        $dbh->rollBack();
    }
    if ($e->getCode() === 409) {
        conflictResponse($e->getMessage());
    } else {
        badRequest($e->getMessage());
    }
} catch (Exception $e) {
    if ($dbh instanceof PDO && $dbh->inTransaction()) {
        $dbh->rollBack();
    }
    error_log("insertOrderByManual.php error: " . $e->getMessage());
    serverError('Failed to create order');
} finally {
    $dbh = null;
}
?>
