<?php
header('Content-Type: application/json');

require_once 'db_helper.php';

$dbh = null;

try {
    $chatid = $_GET['chatid'] ?? null;
    if (!$chatid) {
        throw new Exception('chatid required');
    }
    
    $dbh = getFirebirdConnection();
    $stmt = $dbh->prepare('SELECT MESSAGEID, CHATID, SENDER, MESSAGETEXT, SENTAT FROM CHAT_TPLDTL WHERE CHATID = ? ORDER BY SENTAT ASC');
    $stmt->execute([$chatid]);
    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);
    
    // Format datetime strings
    foreach ($rows as &$row) {
        if ($row['SENTAT']) {
            $row['SENTAT'] = date('Y-m-d H:i:s', strtotime($row['SENTAT']));
        }
    }
    
    echo json_encode(['success' => true, 'data' => $rows]);
} catch (PDOException $e) {
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
} finally {
    $dbh = null;
}
?>
