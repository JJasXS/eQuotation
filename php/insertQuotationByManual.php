<?php
// insertQuotationByManual.php - Create quotation directly from form without chat requirement
header('Content-Type: application/json');
require_once 'db_helper.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    badRequest('POST method required');
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
    
    // MAX+1 is unsafe under concurrency; use a sequence so concurrent sessions cannot collide.
    $quotationid = nextAppId($dbh, 'ORDER_ID');
    
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
            throw new Exception("Invalid item at index $idx");
        }
        
        $quotationdtlid = nextAppId($dbh, 'ORDER_DETAIL_ID');
        
        $detailInsert = $dbh->prepare('
            INSERT INTO ORDER_TPLDTL (ORDERDTLID, ORDERID, DESCRIPTION, QTY, UNITPRICE, DISCOUNT) 
            VALUES (?, ?, ?, ?, ?, ?)
        ');
        $detailInsert->execute([$quotationdtlid, $quotationid, $product, $qty, $price, 0]);
        if ($detailInsert->rowCount() === 0) {
            throw new RuntimeException('No detail row inserted', 409);
        }
    }

    $dbh->commit();
    
    jsonResponse(201, true, 'Quotation created successfully', ['quotationid' => (int)$quotationid], null);

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
    error_log("insertQuotationByManual.php error: " . $e->getMessage());
    serverError('Failed to create quotation');
} finally {
    $dbh = null;
}
?>
