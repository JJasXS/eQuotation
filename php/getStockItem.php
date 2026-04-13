<?php
header('Content-Type: application/json');

require_once 'db_helper.php';

$dbh = null;

try {
    $dbh = getFirebirdConnection();
    // Fetch only columns that exist on this DB to avoid runtime SQL failures across versions.
    $wantedColumns = ['DESCRIPTION', 'STOCKGROUP', 'REMARK1', 'REMARK2', 'UDF_STDPRICE', 'UDF_MOQ', 'UDF_DLEADTIME', 'UDF_BUNDLE'];
    $metaStmt = $dbh->prepare('SELECT TRIM(RF.RDB$FIELD_NAME) AS COL FROM RDB$RELATION_FIELDS RF WHERE RF.RDB$RELATION_NAME = \'ST_ITEM\'');
    $metaStmt->execute();
    $existing = $metaStmt->fetchAll(PDO::FETCH_COLUMN);
    $existingMap = array_fill_keys($existing, true);

    $selectCols = [];
    foreach ($wantedColumns as $col) {
        if (isset($existingMap[$col])) {
            $selectCols[] = $col;
        }
    }

    if (empty($selectCols)) {
        throw new RuntimeException('No expected columns found in ST_ITEM');
    }

    $stmt = $dbh->query('SELECT ' . implode(', ', $selectCols) . ' FROM ST_ITEM');
    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);
    echo json_encode(['success' => true, 'data' => $rows]);
} catch (PDOException $e) {
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
} finally {
    $dbh = null;
}
?>
