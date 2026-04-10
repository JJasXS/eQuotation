<?php
header('Content-Type: application/json');

require_once 'db_helper.php';

$dbh = null;

try {
    $dbh = getFirebirdConnection();
    $stmt = $dbh->query('
        SELECT CODE, DESCRIPTION, UDF_STDPRICE AS STOCKVALUE
        FROM ST_ITEM
        WHERE UDF_STDPRICE > 0
    ');
    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);
    echo json_encode(['success' => true, 'data' => $rows]);
} catch (PDOException $e) {
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
} finally {
    $dbh = null;
}
?>
