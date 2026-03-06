<?php
// checkDraftOrder.php - Check if a chat has an active DRAFT order
require_once 'db_helper.php';

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');

$chatid = $_GET['chatid'] ?? null;

if (!$chatid) {
    echo json_encode(['success' => false, 'error' => 'chatid parameter required']);
    exit;
}

try {
    $con = getFirebirdConnection();
    
    // Check for DRAFT order in this chat
    $query = 'SELECT ORDERID FROM ORDER_TPL WHERE CHATID = ? AND STATUS = ?';
    $stmt = $con->prepare($query);
    $stmt->execute([$chatid, 'DRAFT']);
    $result = $stmt->fetch(PDO::FETCH_ASSOC);
    
    if ($result) {
        echo json_encode([
            'success' => true,
            'hasDraft' => true,
            'orderid' => intval($result['ORDERID'])
        ]);
    } else {
        echo json_encode([
            'success' => true,
            'hasDraft' => false,
            'orderid' => null
        ]);
    }
    
} catch (PDOException $e) {
    echo json_encode(['success' => false, 'error' => 'Database error: ' . $e->getMessage()]);
} catch (Exception $e) {
    echo json_encode(['success' => false, 'error' => 'Error: ' . $e->getMessage()]);
} finally {
    if (isset($con)) {
        $con = null;
    }
}
?>
