<?php
header('Content-Type: application/json');

require_once 'db_helper.php';

$desc = isset($_GET['desc']) ? $_GET['desc'] : '';

try {
    $dbh = getFirebirdConnection();
    $stmt = $dbh->prepare('SELECT DESCRIPTION FROM ST_ITEM WHERE DESCRIPTION LIKE ?');
    $like = "%$desc%";
    $stmt->execute([$like]);
    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);
    echo json_encode(['success' => true, 'data' => $rows]);
} catch (PDOException $e) {
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}
?>
