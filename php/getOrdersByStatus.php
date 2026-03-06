<?php
// getOrdersByStatus.php - Get all orders filtered by status (PENDING, COMPLETED, CANCELLED, DRAFT)
require_once 'db_helper.php';

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');

$status = $_GET['status'] ?? null;
$customerCode = $_GET['customerCode'] ?? null;

if (!$status) {
    echo json_encode(['success' => false, 'error' => 'status parameter required (PENDING, COMPLETED, CANCELLED, or DRAFT)']);
    exit;
}

// Validate status
$validStatuses = ['PENDING', 'COMPLETED', 'CANCELLED', 'DRAFT'];
if (!in_array($status, $validStatuses)) {
    echo json_encode(['success' => false, 'error' => 'Invalid status. Must be PENDING, COMPLETED, CANCELLED, or DRAFT']);
    exit;
}

try {
    $dbh = getFirebirdConnection();
    
    // Get orders with specified status (with optional customer code filter)
    if ($customerCode) {
        // Filter by customer code for regular users
        $stmt = $dbh->prepare('
            SELECT ORDERID, CHATID, OWNEREMAIL, CUSTOMERCODE, CREATEDAT, STATUS 
            FROM ORDER_TPL 
            WHERE STATUS = ? AND CUSTOMERCODE = ? AND (REMARK IS NULL OR REMARK != ?)
            ORDER BY CREATEDAT DESC
        ');
        $stmt->execute([strtoupper($status), $customerCode, 'MANUAL']);
    } else {
        // No filter - for admins (show all orders)
        $stmt = $dbh->prepare('
            SELECT ORDERID, CHATID, OWNEREMAIL, CUSTOMERCODE, CREATEDAT, STATUS 
            FROM ORDER_TPL 
            WHERE STATUS = ? AND (REMARK IS NULL OR REMARK != ?)
            ORDER BY CREATEDAT DESC
        ');
        $stmt->execute([strtoupper($status), 'MANUAL']);
    }
    
    $orders = $stmt->fetchAll(PDO::FETCH_ASSOC);
    
    // Fetch details for each order
    $ordersWithDetails = [];
    foreach ($orders as $order) {
        $dtlStmt = $dbh->prepare('
            SELECT ORDERDTLID, ORDERID, DESCRIPTION, QTY, UNITPRICE, TOTAL, DISCOUNT
            FROM ORDER_TPLDTL
            WHERE ORDERID = ?
            ORDER BY ORDERDTLID
        ');
        $dtlStmt->execute([$order['ORDERID']]);
        $details = $dtlStmt->fetchAll(PDO::FETCH_ASSOC);
        
        // Check if order has change request remarks
        $remarkStmt = $dbh->prepare('
            SELECT COUNT(*) as remark_count
            FROM ORDER_REMARK_TPL
            WHERE ORDERID = ? AND REMARKTYPE = ?
        ');
        $remarkStmt->execute([$order['ORDERID'], 'CHANGE_REQUEST']);
        $remarkCount = $remarkStmt->fetch(PDO::FETCH_ASSOC);
        
        $order['items'] = $details;
        $order['HAS_CHANGE_REQUEST'] = ($remarkCount['REMARK_COUNT'] > 0);
        $ordersWithDetails[] = $order;
    }
    
    echo json_encode([
        'success' => true,
        'status' => strtoupper($status),
        'count' => count($ordersWithDetails),
        'data' => $ordersWithDetails
    ]);
    
} catch (Exception $e) {
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}
?>
