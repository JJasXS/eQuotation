<?php
// updateDraftQuotation.php - Update draft quotation and finalize it
header('Content-Type: application/json');
require_once 'db_helper.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    echo json_encode(['success' => false, 'error' => 'POST method required']);
    exit;
}

$data = json_decode(file_get_contents('php://input'), true);
$dockey = $data['dockey'] ?? null;
$description = $data['description'] ?? null;
$validUntil = $data['validUntil'] ?? null;
$items = $data['items'] ?? [];
$companyName = $data['companyName'] ?? null;
$address1 = $data['address1'] ?? null;
$address2 = $data['address2'] ?? null;
$phone1 = $data['phone1'] ?? null;

if (!$dockey) {
    echo json_encode(['success' => false, 'error' => 'dockey required']);
    exit;
}

if (empty($items)) {
    echo json_encode(['success' => false, 'error' => 'At least one item is required']);
    exit;
}

try {
    $dbh = getFirebirdConnection();
    
    // Verify quotation exists (allow editing of both Pending and Active, but not Cancelled)
    $stmt = $dbh->prepare('SELECT DOCKEY, DOCNO, CODE FROM SL_QT WHERE DOCKEY = ? AND (CANCELLED IS NULL OR CANCELLED = ?)');
    $stmt->execute([$dockey, 'False']);
    $quotation = $stmt->fetch(PDO::FETCH_ASSOC);
    
    if (!$quotation) {
        echo json_encode(['success' => false, 'error' => 'Quotation not found or is cancelled']);
        exit;
    }
    
    $docno = $quotation['DOCNO'];
    $customerCode = $quotation['CODE'];
    
    // Delete existing detail lines
    $deleteStmt = $dbh->prepare('DELETE FROM SL_QTDTL WHERE DOCKEY = ?');
    $deleteStmt->execute([$dockey]);
    
    // Calculate total amount from items
    $totalAmount = 0;
    foreach ($items as $item) {
        $qty = (float)($item['qty'] ?? 0);
        $unitprice = (float)($item['price'] ?? 0);
        $totalAmount += $qty * $unitprice;
    }
    
    // Convert empty string validity to null for date field
    $validityDate = (!empty($validUntil) && $validUntil !== '') ? $validUntil : null;
    
    error_log("[DEBUG] Update params - DOCKEY: $dockey, VALIDITY: " . var_export($validityDate, true) . ", DOCAMT: $totalAmount");
    
    // Update quotation header (don't update STATUS or CANCELLED, just content)
    $updateStmt = $dbh->prepare('
        UPDATE SL_QT 
        SET DESCRIPTION = ?, 
            VALIDITY = ?, 
            DOCAMT = ?,
            COMPANYNAME = ?,
            ADDRESS1 = ?,
            ADDRESS2 = ?,
            PHONE1 = ?
        WHERE DOCKEY = ?
    ');
    
    error_log("[DEBUG] Updating quotation - DOCKEY: $dockey, DOCAMT: $totalAmount, VALIDITY: $validityDate");
    
    $updateStmt->execute([
        $description,
        $validityDate,      // Use converted validity date (null if empty)
        (float)$totalAmount,  // Explicit cast to float
        $companyName,
        $address1,
        $address2,
        $phone1,
        (int)$dockey  // Explicit cast to int
    ]);
    
    // Set quotation to Active (CANCELLED = 'False')
    error_log("[DEBUG] Setting CANCELLED to False for DOCKEY: $dockey");
    $activateStmt = $dbh->prepare('UPDATE SL_QT SET CANCELLED = ? WHERE DOCKEY = ?');
    $activateStmt->execute(['False', (int)$dockey]);
    error_log("[DEBUG] Activation complete");
    
    // Insert new detail lines
    $seq = 1;
    foreach ($items as $idx => $item) {
        $product = $item['product'] ?? '';
        $qty = (float)($item['qty'] ?? 0);
        $unitprice = (float)($item['price'] ?? 0);
        $amount = $qty * $unitprice;
        
        if (!$product || $qty <= 0) {
            echo json_encode(['success' => false, 'error' => "Invalid item at index $idx"]);
            exit;
        }
        
        // Get next DTLKEY (cast to integer to avoid varchar-to-number conversion issues)
        $dtlStmt = $dbh->prepare('SELECT COALESCE(MAX(CAST(DTLKEY AS INTEGER)), 0) + 1 FROM SL_QTDTL');
        $dtlStmt->execute();
        $dtlkey = $dtlStmt->fetchColumn();

        // Resolve ITEMCODE from ST_ITEM using DESCRIPTION first, then CODE
        $itemCode = null;
        $itemLookup = $dbh->prepare('SELECT FIRST 1 CODE FROM ST_ITEM WHERE UPPER(DESCRIPTION) = UPPER(?)');
        $itemLookup->execute([$product]);
        $itemRow = $itemLookup->fetch(PDO::FETCH_ASSOC);

        if ($itemRow && !empty($itemRow['CODE'])) {
            $itemCode = $itemRow['CODE'];
        } else {
            $itemLookupByCode = $dbh->prepare('SELECT FIRST 1 CODE FROM ST_ITEM WHERE UPPER(CODE) = UPPER(?)');
            $itemLookupByCode->execute([$product]);
            $itemCodeRow = $itemLookupByCode->fetch(PDO::FETCH_ASSOC);
            if ($itemCodeRow && !empty($itemCodeRow['CODE'])) {
                $itemCode = $itemCodeRow['CODE'];
            }
        }

        // ITEMCODE must come from ST_ITEM.CODE
        if (!$itemCode) {
            echo json_encode([
                'success' => false,
                'error' => "Item code not found in ST_ITEM for product: {$product}"
            ]);
            exit;
        }

        // DESCRIPTION in SL_QTDTL is VARCHAR(200)
        $itemDescription = mb_substr($product, 0, 200, 'UTF-8');
        
        $detailInsert = $dbh->prepare('
            INSERT INTO SL_QTDTL (
                DTLKEY, DOCKEY, SEQ, ITEMCODE, DESCRIPTION, QTY, 
                UNITPRICE, AMOUNT
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ');
        $detailInsert->execute([
            $dtlkey,
            $dockey,
            $seq,
            $itemCode,
            $itemDescription,
            $qty,
            $unitprice,
            $amount
        ]);
        
        $seq++;
    }
    
    echo json_encode([
        'success' => true,
        'dockey' => $dockey,
        'docno' => $docno,
        'status' => 1,
        'message' => 'Quotation updated successfully'
    ]);
    
} catch (Exception $e) {
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}
?>
