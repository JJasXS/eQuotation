<?php
// getChats.php - Get chats filtered by customer code with latest message sorting
header('Content-Type: application/json');
require_once 'db_helper.php';

$customerCode = $_GET['customerCode'] ?? null;

if (!$customerCode) {
    echo json_encode(['success' => false, 'error' => 'customerCode parameter required']);
    exit;
}

$dbh = null;

try {
    $dbh = getFirebirdConnection();
    
    // Get chats for customer with latest message sorting
    $stmt = $dbh->prepare('
        SELECT c.CHATID, c.CHATNAME, c.CREATEDAT, c.LASTMESSAGE
        FROM CHAT_TPL c
        WHERE c.CUSTOMERCODE = ? AND c.CHATID != 0
        ORDER BY COALESCE(
            (SELECT MAX(d.SENTAT) FROM CHAT_TPLDTL d WHERE d.CHATID = c.CHATID),
            c.CREATEDAT
        ) DESC,
        c.CHATID DESC
    ');
    $stmt->execute([$customerCode]);
    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);
    
    // Format datetime strings
    foreach ($rows as &$row) {
        if ($row['CREATEDAT']) {
            $row['CREATEDAT'] = date('Y-m-d H:i:s', strtotime($row['CREATEDAT']));
        }
    }
    
    echo json_encode(['success' => true, 'chats' => $rows]);
} catch (PDOException $e) {
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
} finally {
    $dbh = null;
}
?>
