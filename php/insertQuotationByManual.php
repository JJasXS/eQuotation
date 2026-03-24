<?php
// insertQuotationByManual.php - Create quotation directly from form without chat requirement
header('Content-Type: application/json');
require_once 'db_helper.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    echo json_encode(['success' => false, 'error' => 'POST method required']);
    exit;
}

$data = json_decode(file_get_contents('php://input'), true);
$ownerEmail = $data['ownerEmail'] ?? null;
$customerCode = $data['customerCode'] ?? null;
$quotationName = $data['quotationName'] ?? 'Manual Quotation';
$validUntil = $data['validUntil'] ?? null;
$items = $data['items'] ?? [];
$companyName = $data['companyName'] ?? null;
$address1 = $data['address1'] ?? null;
$address2 = $data['address2'] ?? null;
$address3 = $data['address3'] ?? null;
$address4 = $data['address4'] ?? null;
$phone1 = $data['phone1'] ?? null;

// DEBUG: Log received data
error_log("DEBUG: insertQuotationByManual received - companyName: $companyName, address1: $address1, address2: $address2, address3: $address3, address4: $address4, phone1: $phone1");

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
    
    // Create or get special MANUAL chat (CHATID = 0 for manual orders/quotations)
    $chatCheckStmt = $dbh->prepare('SELECT CHATID FROM CHAT_TPL WHERE CHATID = ?');
    $chatCheckStmt->execute([0]);
    $manualChat = $chatCheckStmt->fetch(PDO::FETCH_ASSOC);
    
    $manualChatId = 0;
    if (!$manualChat) {
        // Create the dummy chat for manual orders/quotations
        $chatInsert = $dbh->prepare('
            INSERT INTO CHAT_TPL (CHATID, CHATNAME, CREATEDAT, LASTMESSAGE, OWNEREMAIL, CUSTOMERCODE) 
            VALUES (?, ?, ?, ?, ?, ?)
        ');
        $chatInsert->execute([0, 'MANUAL_ORDERS', date('Y-m-d H:i:s'), 'System chat for manual orders', 'system@manual', null]);
        $manualChatId = 0;
    }
    
    // Get next ORDERID (quotations use same table with QUOTATION status)
    $orderStmt = $dbh->prepare('SELECT COALESCE(MAX(ORDERID), 0) + 1 FROM ORDER_TPL');
    $orderStmt->execute();
    $quotationid = $orderStmt->fetchColumn();
    
    $created_at = date('Y-m-d H:i:s');
    
    // Insert quotation header with manual chat ID
    $quotationInsert = $dbh->prepare('
        INSERT INTO ORDER_TPL (ORDERID, CHATID, OWNEREMAIL, CUSTOMERCODE, CREATEDAT, STATUS, REMARK) 
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ');
    $quotationInsert->execute([$quotationid, $manualChatId, $ownerEmail, $customerCode, $created_at, 'QUOTATION', 'MANUAL']);
    
    // Insert quotation details
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
        $quotationdtlid = $detailStmt->fetchColumn();
        
        $detailInsert = $dbh->prepare('
            INSERT INTO ORDER_TPLDTL (ORDERDTLID, ORDERID, DESCRIPTION, QTY, UNITPRICE, DISCOUNT) 
            VALUES (?, ?, ?, ?, ?, ?)
        ');
        $detailInsert->execute([$quotationdtlid, $quotationid, $product, $qty, $price, 0]);
    }
    
    echo json_encode([
        'success' => true,
        'quotationid' => $quotationid,
        'message' => 'Quotation created successfully'
    ]);

} catch (Exception $e) {
    error_log("insertQuotationByManual.php error: " . $e->getMessage());
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}
?>
