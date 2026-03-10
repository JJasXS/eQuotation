<?php
// getQuotationDetails.php - Fetch quotation header and details
require_once 'db_helper.php';

header('Content-Type: application/json');

$dockey = $_GET['dockey'] ?? null;

if (!$dockey) {
    echo json_encode(['success' => false, 'error' => 'dockey required']);
    exit;
}

try {
    $dbh = getFirebirdConnection();
    
    // Get quotation header with customer info joined from AR_CUSTOMER and AR_CUSTOMERBRANCH
    $stmt = $dbh->prepare('
        SELECT q.DOCKEY, q.DOCNO, q.DOCDATE, q.CODE, q.DESCRIPTION, q.DOCAMT, 
               q.CURRENCYCODE, q.VALIDITY, q.STATUS, q.TERMS,
               c.COMPANYNAME, c.CREDITTERM,
               cb.ADDRESS1, cb.ADDRESS2, cb.PHONE1
        FROM SL_QT q
        LEFT JOIN AR_CUSTOMER c ON q.CODE = c.CODE
        LEFT JOIN AR_CUSTOMERBRANCH cb ON q.CODE = cb.CODE
        WHERE q.DOCKEY = ?
    ');
    $stmt->execute([$dockey]);
    $quotation = $stmt->fetch(PDO::FETCH_ASSOC);
    
    if (!$quotation) {
        echo json_encode(['success' => false, 'error' => 'Quotation not found']);
        exit;
    }
    
    // Get quotation details (items)
    $stmt = $dbh->prepare('
        SELECT DTLKEY, DOCKEY, SEQ, ITEMCODE, DESCRIPTION, QTY, 
               UNITPRICE, AMOUNT
        FROM SL_QTDTL 
        WHERE DOCKEY = ? 
        ORDER BY SEQ ASC
    ');
    $stmt->execute([$dockey]);
    $items = $stmt->fetchAll(PDO::FETCH_ASSOC);
    
    // Format items
    $formattedItems = [];
    foreach ($items as $item) {
        $formattedItems[] = [
            'DTLKEY' => intval($item['DTLKEY']),
            'SEQ' => intval($item['SEQ']),
            'ITEMCODE' => $item['ITEMCODE'],
            'DESCRIPTION' => $item['DESCRIPTION'],
            'QTY' => floatval($item['QTY']),
            'UNITPRICE' => floatval($item['UNITPRICE']),
            'AMOUNT' => floatval($item['AMOUNT'] ?? 0)
        ];
    }
    
    // Combine quotation data with items
    $quotationData = [
        'DOCKEY' => intval($quotation['DOCKEY']),
        'DOCNO' => $quotation['DOCNO'],
        'DOCDATE' => $quotation['DOCDATE'],
        'CODE' => $quotation['CODE'],
        'DESCRIPTION' => $quotation['DESCRIPTION'],
        'DOCAMT' => floatval($quotation['DOCAMT']),
        'CURRENCYCODE' => $quotation['CURRENCYCODE'],
        'VALIDITY' => $quotation['VALIDITY'],
        'STATUS' => (string)$quotation['STATUS'],
        'CREDITTERM' => $quotation['CREDITTERM'] ?? 'N/A',
        'COMPANYNAME' => $quotation['COMPANYNAME'] ?? 'N/A',
        'ADDRESS1' => $quotation['ADDRESS1'] ?? 'N/A',
        'ADDRESS2' => $quotation['ADDRESS2'] ?? 'N/A',
        'PHONE1' => $quotation['PHONE1'] ?? 'N/A',
        'items' => $formattedItems
    ];
    
    echo json_encode([
        'success' => true,
        'data' => $quotationData
    ]);
} catch (Exception $e) {
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}
?>
