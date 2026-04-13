<?php
// saveDraftQuotation.php - disabled direct write path for SQL Account shared draft tables.
header('Content-Type: application/json');
require_once 'db_helper.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    badRequest('POST method required');
    exit;
}

// Direct SL_QTDRAFT/SL_QTDTLDRAFT writes previously used MAX+1 key generation, which is unsafe under concurrency.
conflictResponse(
    'Direct insert to shared SQL Account draft tables (SL_QTDRAFT/SL_QTDTLDRAFT) is disabled to prevent key collisions. Use vendor-supported SDK/COM/API flow.',
    ['tables' => ['SL_QTDRAFT', 'SL_QTDTLDRAFT']]
);
?>
