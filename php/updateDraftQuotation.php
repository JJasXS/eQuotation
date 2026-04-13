<?php
// updateDraftQuotation.php - disabled direct write path for SQL Account shared tables.
header('Content-Type: application/json');
require_once 'db_helper.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    badRequest('POST method required');
    exit;
}

// Direct SL_QT/SL_QTDTL writes previously used MAX+1 detail keys, which is unsafe under concurrency.
conflictResponse(
    'Direct write to shared SQL Account tables (SL_QT/SL_QTDTL) is disabled because detail keys cannot be safely generated with MAX+1. Use vendor-supported SDK/COM/API flow.',
    ['tables' => ['SL_QT', 'SL_QTDTL']]
);
?>


