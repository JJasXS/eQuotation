<?php
// updateOrderStatus.php - Update ORDER_TPL status by ORDERID
require_once 'db_helper.php';

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit;
}

$input = json_decode(file_get_contents('php://input'), true);
$orderid = $input['orderid'] ?? null;
$status = strtoupper(trim($input['status'] ?? ''));

if (!$orderid || !$status) {
    http_response_code(400);
    echo json_encode(['success' => false, 'error' => 'orderid and status are required']);
    exit;
}

$validStatuses = ['PENDING', 'COMPLETED', 'CANCELLED'];
if (!in_array($status, $validStatuses)) {
    http_response_code(400);
    echo json_encode(['success' => false, 'error' => 'Invalid status']);
    exit;
}

try {
    $dbh = getFirebirdConnection();

    $stmt = $dbh->prepare('UPDATE ORDER_TPL SET STATUS = ? WHERE ORDERID = ?');
    $stmt->execute([$status, $orderid]);

    if ($stmt->rowCount() === 0) {
        http_response_code(404);
        echo json_encode(['success' => false, 'error' => 'Order not found']);
        exit;
    }

    echo json_encode([
        'success' => true,
        'orderid' => (int)$orderid,
        'status' => $status
    ]);
} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}
?>
