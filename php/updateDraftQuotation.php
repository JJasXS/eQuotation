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
// Default validity: if not provided, use today + 30 days
$udfValidity = (!empty($validUntil) && $validUntil !== '') ? $validUntil : date('Y-m-d', strtotime('+30 days'));
$items = $data['items'] ?? [];
$companyName = $data['companyName'] ?? null;
$address1 = $data['address1'] ?? null;
$address2 = $data['address2'] ?? null;
$address3 = $data['address3'] ?? null;
$address4 = $data['address4'] ?? null;
$postcode = $data['postcode'] ?? null;
$city = $data['city'] ?? null;
$state = $data['state'] ?? null;
$country = $data['country'] ?? null;
$phone1 = $data['phone1'] ?? null;

if (!$dockey) {
    echo json_encode(['success' => false, 'error' => 'dockey required']);
    exit;
}

if (empty($items)) {
    echo json_encode(['success' => false, 'error' => 'At least one item is required']);
    exit;
}

function applyDiscountAmount(float $qty, float $unitprice, float $discAmount): float {
    $lineSubtotal = $qty * $unitprice;
    if ($discAmount <= 0) {
        return max(0, $lineSubtotal);
    }
    return max(0, $lineSubtotal - $discAmount);
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

    // Prefer branch address values from AR_CUSTOMERBRANCH.
    $branchStmt = $dbh->prepare('SELECT FIRST 1 ADDRESS1, ADDRESS2, ADDRESS3, ADDRESS4, POSTCODE, CITY, STATE, COUNTRY, PHONE1 FROM AR_CUSTOMERBRANCH WHERE CODE = ? ORDER BY DTLKEY');
    $branchStmt->execute([$customerCode]);
    $branchRow = $branchStmt->fetch(PDO::FETCH_ASSOC) ?: [];

    $address1 = trim((string)($branchRow['ADDRESS1'] ?? $address1 ?? ''));
    $address2 = trim((string)($branchRow['ADDRESS2'] ?? $address2 ?? ''));
    $address3 = trim((string)($branchRow['ADDRESS3'] ?? $address3 ?? ''));
    $address4 = trim((string)($branchRow['ADDRESS4'] ?? $address4 ?? ''));
    $postcode = trim((string)($branchRow['POSTCODE'] ?? $postcode ?? ''));
    $city = trim((string)($branchRow['CITY'] ?? $city ?? ''));
    $state = trim((string)($branchRow['STATE'] ?? $state ?? ''));
    $country = trim((string)($branchRow['COUNTRY'] ?? $country ?? ''));
    $phone1 = trim((string)($branchRow['PHONE1'] ?? $phone1 ?? ''));
    
    // Delete existing detail lines
    $deleteStmt = $dbh->prepare('DELETE FROM SL_QTDTL WHERE DOCKEY = ?');
    $deleteStmt->execute([$dockey]);
    
    // Calculate total amount from items
    $totalAmount = 0;
    foreach ($items as $item) {
        $qty = (float)($item['qty'] ?? 0);
        $unitprice = (float)($item['price'] ?? 0);
        $disc = (float)($item['discount'] ?? 0);
        $totalAmount += applyDiscountAmount($qty, $unitprice, $disc);
    }
    
    error_log("[DEBUG] Update params - DOCKEY: $dockey, VALIDITY: $udfValidity, DOCAMT: $totalAmount");
    
    // Update quotation header (don't update STATUS or CANCELLED, just content)
    $updateStmt = $dbh->prepare('
        UPDATE SL_QT 
        SET DESCRIPTION = ?, 
            VALIDITY = ?, 
            DOCAMT = ?,
            COMPANYNAME = ?,
            ADDRESS1 = ?,
            ADDRESS2 = ?,
            ADDRESS3 = ?,
            ADDRESS4 = ?,
            POSTCODE = ?,
            CITY = ?,
            STATE = ?,
            COUNTRY = ?,
            PHONE1 = ?
        WHERE DOCKEY = ?
    ');
    
    error_log("[DEBUG] Updating quotation - DOCKEY: $dockey, DOCAMT: $totalAmount, VALIDITY: $udfValidity");
    
    $updateStmt->execute([
        $description,
        $udfValidity,       // VALIDITY: user-supplied or today+30
        (float)$totalAmount,  // Explicit cast to float
        $companyName,
        $address1,
        $address2,
        $address3,
        $address4,
        $postcode,
        $city,
        $state,
        $country,
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
        $disc = (float)($item['discount'] ?? 0);
        $amount = applyDiscountAmount($qty, $unitprice, $disc);
        $deliveryDate = !empty($item['deliveryDate']) ? $item['deliveryDate'] : date('Y-m-d');
        
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
        $itemUom = null;
        $itemRate = null;
        $itemLookup = $dbh->prepare('SELECT FIRST 1 CODE, UDF_UOM FROM ST_ITEM WHERE UPPER(DESCRIPTION) = UPPER(?)');
        $itemLookup->execute([$product]);
        $itemRow = $itemLookup->fetch(PDO::FETCH_ASSOC);

        if ($itemRow && !empty($itemRow['CODE'])) {
            $itemCode = $itemRow['CODE'];
            $itemUom = trim((string)($itemRow['UDF_UOM'] ?? ''));
        } else {
            $itemLookupByCode = $dbh->prepare('SELECT FIRST 1 CODE, UDF_UOM FROM ST_ITEM WHERE UPPER(CODE) = UPPER(?)');
            $itemLookupByCode->execute([$product]);
            $itemCodeRow = $itemLookupByCode->fetch(PDO::FETCH_ASSOC);
            if ($itemCodeRow && !empty($itemCodeRow['CODE'])) {
                $itemCode = $itemCodeRow['CODE'];
                $itemUom = trim((string)($itemCodeRow['UDF_UOM'] ?? ''));
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

        if ($itemCode && $itemUom !== '') {
            $rateLookup = $dbh->prepare('SELECT FIRST 1 RATE FROM ST_ITEM_UOM WHERE CODE = ? AND UOM = ?');
            $rateLookup->execute([$itemCode, $itemUom]);
            $resolvedRate = $rateLookup->fetchColumn();
            if ($resolvedRate !== false && $resolvedRate !== null) {
                $itemRate = (float)$resolvedRate;
            }
        }

        // DESCRIPTION in SL_QTDTL is VARCHAR(200)
        $itemDescription = mb_substr($product, 0, 200, 'UTF-8');
        
        $detailInsert = $dbh->prepare('
            INSERT INTO SL_QTDTL (
                DTLKEY, DOCKEY, SEQ, ITEMCODE, DESCRIPTION, QTY, 
                UOM, RATE, UNITPRICE, DISC, AMOUNT, UDF_STDPRICE, DELIVERYDATE, IRBM_CLASSIFICATION
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ');
        $detailInsert->execute([
            $dtlkey,
            $dockey,
            $seq,
            $itemCode,
            $itemDescription,
            $qty,
            $itemUom !== '' ? $itemUom : null,
            $itemRate,
            $unitprice,
            $disc,
            $amount,
            null,
            $deliveryDate,
            '022'
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


