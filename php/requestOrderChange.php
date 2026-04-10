<?php
header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit;
}

require_once 'db_helper.php';

// Get JSON input before opening DB connection.
$input = json_decode(file_get_contents('php://input'), true);

if (!isset($input['orderid']) || !isset($input['remark']) || !isset($input['requestedby'])) {
    echo json_encode([
        'success' => false,
        'error' => 'Missing required parameters: orderid, remark, and requestedby'
    ]);
    exit;
}

$orderid = (int)$input['orderid'];
$remark = trim($input['remark']);
$requestedby = trim($input['requestedby']);

if (empty($remark)) {
    echo json_encode([
        'success' => false,
        'error' => 'Remark cannot be empty'
    ]);
    exit;
}

$conn = null;

try {
    $conn = getFirebirdConnection();
    
    // Begin transaction
    $conn->beginTransaction();
    
    // Insert remark into ORDER_REMARK_TPL
    $insertQuery = "INSERT INTO ORDER_REMARK_TPL (ORDERID, REMARK, REQUESTEDBY, REMARKTYPE) 
                    VALUES (?, ?, ?, ?)";
    
    $stmt = $conn->prepare($insertQuery);
    if (!$stmt) {
        throw new Exception('Failed to prepare insert statement');
    }
    
    $result = $stmt->execute([$orderid, $remark, $requestedby, 'CHANGE_REQUEST']);
    if (!$result) {
        throw new Exception('Failed to insert remark');
    }
    
    // Update order status to PENDING
    $updateQuery = "UPDATE ORDER_TPL SET STATUS = 'PENDING' WHERE ORDERID = ?";
    
    $stmt2 = $conn->prepare($updateQuery);
    if (!$stmt2) {
        throw new Exception('Failed to prepare update statement');
    }
    
    $result2 = $stmt2->execute([$orderid]);
    if (!$result2) {
        throw new Exception('Failed to update order status');
    }
    
    // Commit transaction
    $conn->commit();
    
    echo json_encode([
        'success' => true,
        'message' => 'Order change request submitted successfully'
    ]);
    
} catch (Exception $e) {
    if ($conn instanceof PDO && $conn->inTransaction()) {
        $conn->rollBack();
    }
    echo json_encode([
        'success' => false,
        'error' => $e->getMessage()
    ]);
} finally {
    $conn = null;
}
?>
