<?php
// insertOrderDetail.php - Add line item to order
require_once 'db_helper.php';

header('Content-Type: application/json');

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    badRequest('POST method required');
    exit;
}

$data = json_decode(file_get_contents('php://input'), true);
$orderid = $data['orderid'] ?? null;
$description = $data['description'] ?? null;
$qty = $data['qty'] ?? null;
$unitprice = $data['unitprice'] ?? null;
$discount = $data['discount'] ?? 0;

if (!$orderid || !$description || !$qty || !$unitprice) {
    badRequest('orderid, description, qty, unitprice required');
    exit;
}

$dbh = null;

try {
    $dbh = getFirebirdConnection();
    $dbh->beginTransaction();
    
    // Verify parent header exists before inserting a child row.
    $orderStmt = $dbh->prepare('SELECT ORDERID FROM ORDER_TPL WHERE ORDERID = ?');
    $orderStmt->execute([$orderid]);
    if (!$orderStmt->fetchColumn()) {
        throw new RuntimeException('Order not found', 404);
    }

    // Calculate total
    $total = ($qty * $unitprice) - $discount;

    // MAX+1 is unsafe under concurrency; use a sequence so concurrent sessions cannot collide.
    $orderdtlid = nextAppId($dbh, 'ORDER_DETAIL_ID');
    
    // Insert order detail
    $stmt = $dbh->prepare('
        INSERT INTO ORDER_TPLDTL (ORDERDTLID, ORDERID, DESCRIPTION, QTY, UNITPRICE, TOTAL, DISCOUNT) 
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ');
    $stmt->execute([(int)$orderdtlid, $orderid, $description, $qty, $unitprice, $total, $discount]);
    if ($stmt->rowCount() === 0) {
        throw new RuntimeException('No detail row inserted', 409);
    }
    $dbh->commit();
    
    jsonResponse(201, true, 'Order detail created', [
        'orderdtlid' => (int)$orderdtlid,
        'total' => (float)$total,
    ], null);
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
    serverError('Failed to create order detail');
} finally {
    $dbh = null;
}
?>
