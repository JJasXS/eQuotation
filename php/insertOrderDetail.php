<?php
// insertOrderDetail.php - Add line item to order
require_once 'db_helper.php';

header('Content-Type: application/json');

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    echo json_encode(['success' => false, 'error' => 'POST method required']);
    exit;
}

$data = json_decode(file_get_contents('php://input'), true);
$orderid = $data['orderid'] ?? null;
$description = $data['description'] ?? null;
$qty = $data['qty'] ?? null;
$unitprice = $data['unitprice'] ?? null;
$discount = $data['discount'] ?? 0;

if (!$orderid || !$description || !$qty || !$unitprice) {
    echo json_encode(['success' => false, 'error' => 'orderid, description, qty, unitprice required']);
    exit;
}

$dbh = null;

try {
    $dbh = getFirebirdConnection();
    $dbh->beginTransaction();
    
    // Calculate total
    $total = ($qty * $unitprice) - $discount;
    
    // Get next ORDERDTLID
    $stmt = $dbh->prepare('SELECT COALESCE(MAX(ORDERDTLID), 0) + 1 AS nextid FROM ORDER_TPLDTL');
    $stmt->execute();
    $result = $stmt->fetch(PDO::FETCH_ASSOC);
    $orderdtlid = $result['nextid'] ?? $result['NEXTID'] ?? null;

    if ($orderdtlid === null) {
        throw new Exception('Failed to generate next ORDERDTLID');
    }
    
    // Insert order detail
    $stmt = $dbh->prepare('
        INSERT INTO ORDER_TPLDTL (ORDERDTLID, ORDERID, DESCRIPTION, QTY, UNITPRICE, TOTAL, DISCOUNT) 
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ');
    $stmt->execute([(int)$orderdtlid, $orderid, $description, $qty, $unitprice, $total, $discount]);
    $dbh->commit();
    
    echo json_encode([
        'success' => true,
        'orderdtlid' => $orderdtlid,
        'total' => $total,
        'message' => "Added $qty x $description"
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
