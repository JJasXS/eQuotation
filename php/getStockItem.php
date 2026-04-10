<?php
header('Content-Type: application/json');

require_once 'db_helper.php';

$dbh = null;

try {
    $dbh = getFirebirdConnection();
    // Fetch stock item details including UDF fields for chatbot
    $stmt = $dbh->query('
        SELECT 
            DESCRIPTION, 
            STOCKGROUP, 
            REMARK1, 
            REMARK2,
            UDF_STDPRICE,
            UDF_MOQ,
            UDF_DLEADTIME,
            UDF_BUNDLE
        FROM ST_ITEM
    ');
    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);
    echo json_encode(['success' => true, 'data' => $rows]);
} catch (PDOException $e) {
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
} finally {
    $dbh = null;
}
?>
