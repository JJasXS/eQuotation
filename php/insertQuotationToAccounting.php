<?php
// insertQuotationToAccounting.php - disabled direct write path for SQL Account shared tables.
header('Content-Type: application/json');
require_once 'db_helper.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    badRequest('POST method required');
    exit;
}

// Direct SL_QT/SL_QTDTL inserts previously used MAX+1 key generation, which is unsafe under concurrency.
conflictResponse(
    'Direct insert to shared SQL Account tables (SL_QT/SL_QTDTL) is disabled to prevent key collisions. Use vendor-supported SDK/COM/API flow.',
    ['tables' => ['SL_QT', 'SL_QTDTL']]
);
?>



