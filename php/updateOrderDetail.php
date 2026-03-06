<?php
// updateOrderDetail.php - Update line item quantity/price
require_once 'db_helper.php';

header('Content-Type: application/json');

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    echo json_encode(['success' => false, 'error' => 'POST method required']);
    exit;
}

$data = json_decode(file_get_contents('php://input'), true);
$orderdtlid = $data['orderdtlid'] ?? null;
$description = $data['description'] ?? null;
$qty = $data['qty'] ?? null;
$unitprice = $data['unitprice'] ?? null;
$discount = $data['discount'] ?? 0;

if (!$orderdtlid || $qty === null) {
    echo json_encode(['success' => false, 'error' => 'orderdtlid and qty required']);
    exit;
}

try {
    $dbh = getFirebirdConnection();
    
    // Get current details if unitprice not provided
    if ($unitprice === null) {
        $stmt = $dbh->prepare('SELECT UNITPRICE FROM ORDER_TPLDTL WHERE ORDERDTLID = ?');
        $stmt->execute([$orderdtlid]);
        $result = $stmt->fetch(PDO::FETCH_ASSOC);
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
    
    echo json_encode([
        'success' => true,
        'total' => $total,
        'message' => "Updated quantity to $qty"
    ]);
} catch (Exception $e) {
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}
?>
