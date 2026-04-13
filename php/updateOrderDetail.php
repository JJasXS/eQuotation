<?php
// updateOrderDetail.php - Update line item quantity/price
require_once 'db_helper.php';

header('Content-Type: application/json');

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    badRequest('POST method required');
    exit;
}

$data = json_decode(file_get_contents('php://input'), true);
$orderdtlid = $data['orderdtlid'] ?? null;
$description = $data['description'] ?? null;
$qty = $data['qty'] ?? null;
$unitprice = $data['unitprice'] ?? null;
$discount = $data['discount'] ?? 0;

if (!$orderdtlid || $qty === null) {
    badRequest('orderdtlid and qty required');
    exit;
}

$dbh = null;

try {
    $dbh = getFirebirdConnection();
    $dbh->beginTransaction();
    
    // Get current details if unitprice not provided
    if ($unitprice === null) {
        $stmt = $dbh->prepare('SELECT UNITPRICE FROM ORDER_TPLDTL WHERE ORDERDTLID = ?');
        $stmt->execute([$orderdtlid]);
        $result = $stmt->fetch(PDO::FETCH_ASSOC);
        if (!$result) {
            throw new RuntimeException('Order detail not found', 404);
        }
        $unitprice = $result['UNITPRICE'] ?? 0;
    }
    
    // Calculate total
    $total = ($qty * $unitprice) - $discount;
    
    // Update order detail
    $stmt = $dbh->prepare('
        UPDATE ORDER_TPLDTL 
        SET DESCRIPTION = ?, QTY = ?, UNITPRICE = ?, TOTAL = ?, DISCOUNT = ? 
        WHERE ORDERDTLID = ?
    ');
    $stmt->execute([$description, $qty, $unitprice, $total, $discount, $orderdtlid]);
    if ($stmt->rowCount() === 0) {
        throw new RuntimeException('Order detail not found or no changes applied', 404);
    }

    $dbh->commit();
    
    jsonResponse(200, true, "Updated quantity to $qty", ['total' => (float)$total], null);
} catch (RuntimeException $e) {
    if ($dbh instanceof PDO && $dbh->inTransaction()) {
        $dbh->rollBack();
    }
    if ($e->getCode() === 404) {
        notFound($e->getMessage());
    } else {
        badRequest($e->getMessage());
    }
} catch (Exception $e) {
    if ($dbh instanceof PDO && $dbh->inTransaction()) {
        $dbh->rollBack();
    }
    serverError('Failed to update order detail');
} finally {
    $dbh = null;
}
?>
