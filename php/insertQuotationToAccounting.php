<?php
// insertQuotationToAccounting.php - Create quotation in SL_QT and SL_QTDTL tables
header('Content-Type: application/json');
require_once 'db_helper.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    echo json_encode(['success' => false, 'error' => 'POST method required']);
    exit;
}

$data = json_decode(file_get_contents('php://input'), true);
$customerCode = $data['customerCode'] ?? null;
$description = $data['description'] ?? null;
$validUntil = $data['validUntil'] ?? null;
$items = $data['items'] ?? [];
$currencyCode = $data['currencyCode'] ?? 'MYR';
$companyName = $data['companyName'] ?? null;
$address1 = $data['address1'] ?? null;
$address2 = $data['address2'] ?? null;
$phone1 = $data['phone1'] ?? null;

// DEBUG: Log received data
error_log("DEBUG: insertQuotationToAccounting received - companyName: $companyName, address1: $address1, address2: $address2, phone1: $phone1");

if (!$customerCode) {
    echo json_encode(['success' => false, 'error' => 'customerCode required']);
    exit;
}

if (empty($items)) {
    echo json_encode(['success' => false, 'error' => 'At least one item is required']);
    exit;
}

function applyPercentageDiscount(float $qty, float $unitprice, float $discPct): float {
    $lineSubtotal = $qty * $unitprice;
    if ($discPct <= 0) {
        return max(0, $lineSubtotal);
    }
    $discountAmount = $lineSubtotal * ($discPct / 100.0);
    return max(0, $lineSubtotal - $discountAmount);
}

try {
    $dbh = getFirebirdConnection();
    
    // Fetch CREDITTERM from AR_CUSTOMER (store into SL_QT.TERMS)
    $termsStmt = $dbh->prepare('SELECT CREDITTERM FROM AR_CUSTOMER WHERE CODE = ?');
    $termsStmt->execute([$customerCode]);
    $terms = $termsStmt->fetchColumn();
    $terms = $terms ?: 'N/A';
    
    // Get next DOCKEY
    $stmt = $dbh->prepare('SELECT COALESCE(MAX(DOCKEY), 0) + 1 FROM SL_QT');
    $stmt->execute();
    $dockey = $stmt->fetchColumn();
    
    // Generate DOCNO as QT-0001, QT-0002 format
    $docNoStmt = $dbh->prepare("SELECT MAX(CAST(SUBSTRING(DOCNO FROM 4) AS INTEGER)) AS MAXNO FROM SL_QT WHERE DOCNO STARTING WITH 'QT-'");
    $docNoStmt->execute();
    $maxDocNo = $docNoStmt->fetchColumn();
    $nextDocNo = ($maxDocNo !== null && $maxDocNo !== false) ? ((int)$maxDocNo + 1) : 1;
    $docno = 'QT-' . str_pad($nextDocNo, 4, '0', STR_PAD_LEFT);
    
    // Calculate total amount from items
    $totalAmount = 0;
    foreach ($items as $item) {
        $qty = (float)($item['qty'] ?? 0);
        $unitprice = (float)($item['price'] ?? 0);
        $disc = (float)($item['discount'] ?? 0);
        $totalAmount += applyPercentageDiscount($qty, $unitprice, $disc);
    }
    
    $docDate = date('Y-m-d');
    $quotationStatus = 0; // 0 = DRAFT, 1 = COMPLETED
    
    // Insert quotation header into SL_QT
    $qtStmt = $dbh->prepare('
        INSERT INTO SL_QT (
            DOCKEY, DOCNO, DOCDATE, CODE, DESCRIPTION, DOCAMT, 
            CURRENCYCODE, VALIDITY, SHIPPER, STATUS, TERMS, COMPANYNAME, ADDRESS1, ADDRESS2, PHONE1, CANCELLED
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ');
    
    // DEBUG: Log values before insert
    error_log("DEBUG: About to insert - companyName: $companyName, address1: $address1, address2: $address2, phone1: $phone1");
    
    try {
        $qtStmt->execute([
            $dockey,
            $docno,
            $docDate,
            $customerCode,
            $description,
            $totalAmount,
            $currencyCode,
            $validUntil,
            'AUTO',  // Default shipper
            $quotationStatus,
            $terms,
            $companyName,
            $address1,
            $address2,
            $phone1,
            null
        ]);
        error_log("DEBUG: Insert successful for dockey: $dockey");
    } catch (PDOException $e) {
        error_log("DEBUG: Insert failed - " . $e->getMessage());
        echo json_encode(['success' => false, 'error' => 'Database insert error: ' . $e->getMessage()]);
        exit;
    }
    
    // Insert quotation detail lines into SL_QTDTL
    $seq = 1;
    foreach ($items as $idx => $item) {
        $product = $item['product'] ?? '';
        $qty = (float)($item['qty'] ?? 0);
        $unitprice = (float)($item['price'] ?? 0);
        $disc = (float)($item['discount'] ?? 0);
        $suggestedPrice = (float)($item['suggestedPrice'] ?? $unitprice);
        $amount = applyPercentageDiscount($qty, $unitprice, $disc);
        
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
                UNITPRICE, DISC, AMOUNT, UDF_STDPRICE
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ');
        $detailInsert->execute([
            $dtlkey,
            $dockey,
            $seq,
            $itemCode,
            $itemDescription,
            $qty,
            $unitprice,
            $disc,
            $amount,
            $suggestedPrice
        ]);
        
        $seq++;
    }

    // Move quotation status to COMPLETED (1) once all lines are inserted successfully
    $completeStmt = $dbh->prepare('UPDATE SL_QT SET STATUS = ? WHERE DOCKEY = ?');
    $completeStmt->execute([1, $dockey]); // 1 = COMPLETED
    
    echo json_encode([
        'success' => true,
        'dockey' => $dockey,
        'docno' => $docno,
        'status' => 1,
        'message' => 'Quotation created successfully'
    ]);
    
} catch (Exception $e) {
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}
?>
