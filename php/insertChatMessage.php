<?php
header('Content-Type: application/json');

require_once 'db_helper.php';

$dbh = null;

try {
    $data = json_decode(file_get_contents('php://input'), true);
    $chatid = $data['chatid'] ?? null;
    $sender = $data['sender'] ?? null;
    $messagetext = $data['messagetext'] ?? null;
    
    if (!$chatid || !$sender || !$messagetext) {
        echo json_encode(['success' => false, 'error' => 'chatid, sender, and messagetext required']);
        exit;
    }
    
    $dbh = getFirebirdConnection();
    $dbh->beginTransaction();
    
    // Get next MESSAGEID
    $stmt = $dbh->query('SELECT COALESCE(MAX(MESSAGEID), 0) + 1 FROM CHAT_TPLDTL');
    $messageid = $stmt->fetchColumn();
    
    // Insert message
    $stmt = $dbh->prepare('INSERT INTO CHAT_TPLDTL (MESSAGEID, CHATID, SENDER, MESSAGETEXT, SENTAT) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)');
    $stmt->execute([$messageid, $chatid, $sender, $messagetext]);
    
    // Update LASTMESSAGE in CHAT_TPL
    $stmt = $dbh->prepare('UPDATE CHAT_TPL SET LASTMESSAGE = ? WHERE CHATID = ?');
    $stmt->execute([$messagetext, $chatid]);
    
    $dbh->commit();
    
    echo json_encode(['success' => true, 'messageid' => $messageid]);
} catch (PDOException $e) {
    if ($dbh instanceof PDO && $dbh->inTransaction()) {
        $dbh->rollBack();
    }
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
} finally {
    $dbh = null;
}
?>
