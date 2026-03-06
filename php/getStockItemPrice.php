<?php
header('Content-Type: application/json');

require_once 'db_helper.php';

try {
    $dbh = getFirebirdConnection();
    $stmt = $dbh->query('
        SELECT p.CODE, i.DESCRIPTION, p.STOCKVALUE 
        FROM ST_ITEM_PRICE p
        LEFT JOIN ST_ITEM i ON p.CODE = i.CODE
        WHERE p.STOCKVALUE > 0
    ');
    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);
    echo json_encode(['success' => true, 'data' => $rows]);
} catch (PDOException $e) {
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}
?>
