<?php
// insertOrder.php - Create a new order
require_once 'db_helper.php';

header('Content-Type: application/json');

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    badRequest('POST method required');
    exit;
}

$data = json_decode(file_get_contents('php://input'), true);
$chatid = $data['chatid'] ?? null;

if (!$chatid) {
    badRequest('chatid required');
    exit;
}

$dbh = null;

try {
    $dbh = getFirebirdConnection();
    $dbh->beginTransaction();

    // Resolve chat owner email and customer code
    $ownerStmt = $dbh->prepare('SELECT OWNEREMAIL, CUSTOMERCODE FROM CHAT_TPL WHERE CHATID = ?');
    $ownerStmt->execute([$chatid]);
    $ownerRow = $ownerStmt->fetch(PDO::FETCH_ASSOC);

    if (!$ownerRow) {
        throw new RuntimeException('Chat not found', 404);
    }

    $ownerEmail = $ownerRow['OWNEREMAIL'] ?? null;
    $customerCode = $ownerRow['CUSTOMERCODE'] ?? null;
    
    // FIRST: Check if there's already a DRAFT order for this chatid
    $stmt = $dbh->prepare('SELECT ORDERID FROM ORDER_TPL WHERE CHATID = ? AND STATUS = ?');
    $stmt->execute([$chatid, 'DRAFT']);
    $existing = $stmt->fetch(PDO::FETCH_ASSOC);
    
    if ($existing) {
        $dbh->commit();
        jsonResponse(200, true, 'Using existing draft order', ['orderid' => (int)$existing['ORDERID']], null);
        return;
    }

    // MAX+1 is unsafe under concurrency; use a sequence so concurrent sessions cannot collide.
    $orderid = nextAppId($dbh, 'ORDER_ID');
    
    // Insert new order with current timestamp and customer code
    $created_at = date('Y-m-d H:i:s');
    $stmt = $dbh->prepare('
        INSERT INTO ORDER_TPL (ORDERID, CHATID, OWNEREMAIL, CUSTOMERCODE, CREATEDAT, STATUS) 
        VALUES (?, ?, ?, ?, ?, ?)
    ');
    $stmt->execute([$orderid, $chatid, $ownerEmail, $customerCode, $created_at, 'DRAFT']);
    $dbh->commit();
    
    jsonResponse(201, true, 'Order created successfully', ['orderid' => (int)$orderid], null);
} catch (RuntimeException $e) {
    if ($dbh instanceof PDO && $dbh->inTransaction()) {
        $dbh->rollBack();
    }
    if ($e->getCode() === 404) {
        notFound($e->getMessage());
    } elseif ($e->getCode() === 409) {
        conflictResponse($e->getMessage());
    } else {
        badRequest($e->getMessage());
    }
} catch (Exception $e) {
    if ($dbh instanceof PDO && $dbh->inTransaction()) {
        $dbh->rollBack();
    }
    error_log("insertOrder.php error: " . $e->getMessage());
    serverError('Failed to create order');
} finally {
    $dbh = null;
}
?>
