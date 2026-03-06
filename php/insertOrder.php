<?php
// insertOrder.php - Create a new order
require_once 'db_helper.php';

header('Content-Type: application/json');

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    echo json_encode(['success' => false, 'error' => 'POST method required']);
    exit;
}

$data = json_decode(file_get_contents('php://input'), true);
$chatid = $data['chatid'] ?? null;

if (!$chatid) {
    echo json_encode(['success' => false, 'error' => 'chatid required']);
    exit;
}

try {
    $dbh = getFirebirdConnection();

    // Resolve chat owner email and customer code
    $ownerStmt = $dbh->prepare('SELECT OWNEREMAIL, CUSTOMERCODE FROM CHAT_TPL WHERE CHATID = ?');
    $ownerStmt->execute([$chatid]);
    $ownerRow = $ownerStmt->fetch(PDO::FETCH_ASSOC);

    if (!$ownerRow) {
        echo json_encode(['success' => false, 'error' => 'Chat not found']);
        exit;
    }

    $ownerEmail = $ownerRow['OWNEREMAIL'] ?? null;
    $customerCode = $ownerRow['CUSTOMERCODE'] ?? null;
    
    // FIRST: Check if there's already a DRAFT order for this chatid
    $stmt = $dbh->prepare('SELECT ORDERID FROM ORDER_TPL WHERE CHATID = ? AND STATUS = ?');
    $stmt->execute([$chatid, 'DRAFT']);
    $existing = $stmt->fetch(PDO::FETCH_ASSOC);
    
    if ($existing) {
        // Return existing DRAFT order instead of creating duplicate
        echo json_encode([
            'success' => true,
            'orderid' => $existing['ORDERID'],
            'message' => 'Using existing draft order'
        ]);
        exit;
    }
    
    // Get next ORDERID - Firebird column names might be case-sensitive
    $query = 'SELECT MAX(ORDERID) FROM ORDER_TPL';
    $stmt = $dbh->query($query);
    $max_id = $stmt->fetchColumn();
    
    // Debug: log what we got
    error_log("Max ORDERID found: " . var_export($max_id, true));
    
    // Handle NULL (no rows) or actual max value
    if ($max_id === null || $max_id === false) {
        $orderid = 1;
    } else {
        $orderid = (int)$max_id + 1;
    }
    
    error_log("Next ORDERID to use: " . $orderid);
    
    // Insert new order with current timestamp and customer code
    $created_at = date('Y-m-d H:i:s');
    $stmt = $dbh->prepare('
        INSERT INTO ORDER_TPL (ORDERID, CHATID, OWNEREMAIL, CUSTOMERCODE, CREATEDAT, STATUS) 
        VALUES (?, ?, ?, ?, ?, ?)
    ');
    $stmt->execute([$orderid, $chatid, $ownerEmail, $customerCode, $created_at, 'DRAFT']);
    
    echo json_encode([
        'success' => true,
        'orderid' => $orderid,
        'message' => 'Order created successfully'
    ]);
} catch (Exception $e) {
    $error_details = $e->getMessage();
    error_log("insertOrder.php error: " . $error_details);
    echo json_encode(['success' => false, 'error' => $error_details]);
}
?>
