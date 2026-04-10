<?php
header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');

require_once 'db_helper.php';

$conn = null;

try {
    $conn = getFirebirdConnection();
    
    if (!isset($_GET['orderid'])) {
        throw new Exception('Missing required parameter: orderid');
    }
    
    $orderid = (int)$_GET['orderid'];
    
    // Get all remarks for the order
    $query = "SELECT REMARKID, ORDERID, REMARK, REQUESTEDBY, REMARKTYPE, CREATEDAT 
              FROM ORDER_REMARK_TPL 
              WHERE ORDERID = ?
              ORDER BY CREATEDAT DESC";
    
    $stmt = $conn->prepare($query);
    if (!$stmt) {
        throw new Exception('Failed to prepare query');
    }
    
    $result = $stmt->execute([$orderid]);
    if (!$result) {
        throw new Exception('Failed to execute query');
    }
    
    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);
    $remarks = [];
    foreach ($rows as $row) {
        $remarks[] = [
            'REMARKID' => $row['REMARKID'],
            'ORDERID' => $row['ORDERID'],
            'REMARK' => trim($row['REMARK']),
            'REQUESTEDBY' => trim($row['REQUESTEDBY'] ?? ''),
            'REMARKTYPE' => trim($row['REMARKTYPE'] ?? ''),
            'CREATEDAT' => $row['CREATEDAT']
        ];
    }
    
    echo json_encode([
        'success' => true,
        'data' => $remarks
    ]);
    
} catch (Exception $e) {
    echo json_encode([
        'success' => false,
        'error' => $e->getMessage()
    ]);
} finally {
    $conn = null;
}
?>
