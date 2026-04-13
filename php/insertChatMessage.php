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
        badRequest('chatid, sender, and messagetext are required');
        return;
    }
    
    $dbh = getFirebirdConnection();
    $dbh->beginTransaction();
    
    // MAX+1 is unsafe under concurrency; use a sequence so concurrent sessions cannot collide.
    $messageid = nextAppId($dbh, 'CHAT_MESSAGE_ID');

    // Ensure parent chat exists before writing child row.
    $chatStmt = $dbh->prepare('SELECT CHATID FROM CHAT_TPL WHERE CHATID = ?');
    $chatStmt->execute([$chatid]);
    if (!$chatStmt->fetchColumn()) {
        throw new RuntimeException('Chat not found', 404);
    }
    
    // Insert message
    $stmt = $dbh->prepare('INSERT INTO CHAT_TPLDTL (MESSAGEID, CHATID, SENDER, MESSAGETEXT, SENTAT) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)');
    $stmt->execute([$messageid, $chatid, $sender, $messagetext]);
    
    // Update LASTMESSAGE in CHAT_TPL
    $stmt = $dbh->prepare('UPDATE CHAT_TPL SET LASTMESSAGE = ? WHERE CHATID = ?');
    $stmt->execute([$messagetext, $chatid]);
    if ($stmt->rowCount() === 0) {
        throw new RuntimeException('Chat not found', 404);
    }
    
    $dbh->commit();
    
    jsonResponse(201, true, 'Message created', ['messageid' => (int)$messageid], null);
} catch (PDOException $e) {
    if ($dbh instanceof PDO && $dbh->inTransaction()) {
        $dbh->rollBack();
    }
    serverError('Database error while creating message');
} catch (RuntimeException $e) {
    if ($dbh instanceof PDO && $dbh->inTransaction()) {
        $dbh->rollBack();
    }
    if ($e->getCode() === 404) {
        notFound($e->getMessage());
    } elseif ($e->getCode() === 409) {
        conflictResponse($e->getMessage());
    } else {
        badRequest($e->getMessage());
    }
} finally {
    $dbh = null;
}
?>
