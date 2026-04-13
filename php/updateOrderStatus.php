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
    badRequest('orderid and status are required');
    exit;
}

$validStatuses = ['PENDING', 'COMPLETED', 'CANCELLED'];
if (!in_array($status, $validStatuses)) {
    badRequest('Invalid status');
    exit;
}

$dbh = null;

try {
    $dbh = getFirebirdConnection();
    $dbh->beginTransaction();

    $findStmt = $dbh->prepare('SELECT STATUS FROM ORDER_TPL WHERE ORDERID = ?');
    $findStmt->execute([$orderid]);
    $currentStatus = $findStmt->fetchColumn();
    if ($currentStatus === false) {
        throw new RuntimeException('Order not found', 404);
    }

    // Defensive transition rules to reduce accidental state corruption.
    $allowedTransitions = [
        'DRAFT' => ['PENDING', 'CANCELLED'],
        'PENDING' => ['COMPLETED', 'CANCELLED'],
        'COMPLETED' => [],
        'CANCELLED' => [],
    ];
    $currentStatusNorm = strtoupper(trim((string)$currentStatus));
    if (!isset($allowedTransitions[$currentStatusNorm]) || !in_array($status, $allowedTransitions[$currentStatusNorm], true)) {
        throw new RuntimeException('Invalid status transition from ' . $currentStatusNorm . ' to ' . $status, 409);
    }

    $stmt = $dbh->prepare('UPDATE ORDER_TPL SET STATUS = ? WHERE ORDERID = ?');
    $stmt->execute([$status, $orderid]);

    if ($stmt->rowCount() === 0) {
        throw new RuntimeException('Order not found', 404);
    }

    $dbh->commit();

    jsonResponse(200, true, 'Order status updated', ['orderid' => (int)$orderid, 'status' => $status], null);
} catch (Exception $e) {
    if ($dbh instanceof PDO && $dbh->inTransaction()) {
        $dbh->rollBack();
    }
    if ($e->getCode() === 404) {
        notFound($e->getMessage());
    } elseif ($e->getCode() === 409) {
        conflictResponse($e->getMessage());
    } else {
        serverError('Failed to update status');
    }
} finally {
    $dbh = null;
}
?>
