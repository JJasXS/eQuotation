<?php
header('Content-Type: application/json');

require_once 'db_helper.php';

try {
    $dbh = getFirebirdConnection();
    $stmt = $dbh->query('SELECT DESCRIPTION, STOCKGROUP FROM ST_ITEM');
    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);
    echo json_encode(['success' => true, 'data' => $rows]);
} catch (PDOException $e) {
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}
?>
