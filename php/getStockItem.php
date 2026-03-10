<?php
header('Content-Type: application/json');

require_once 'db_helper.php';

try {
    $dbh = getFirebirdConnection();
    // Fetch DESCRIPTION, STOCKGROUP, REMARK1, REMARK2 if present
    $stmt = $dbh->query('SELECT DESCRIPTION, STOCKGROUP, REMARK1, REMARK2 FROM ST_ITEM');
    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);
    echo json_encode(['success' => true, 'data' => $rows]);
} catch (PDOException $e) {
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}
?>
