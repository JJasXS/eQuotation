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
$draftDockey = $data['draftDockey'] ?? null;

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

function applyDiscountAmount(float $qty, float $unitprice, float $discAmount): float {
    $lineSubtotal = $qty * $unitprice;
    if ($discAmount <= 0) {
        return max(0, $lineSubtotal);
    }
    return max(0, $lineSubtotal - $discAmount);
}

try {
    $dbh = getFirebirdConnection();
    
    // Fetch CREDITTERM, CURRENCYCODE, AGENT, AREA, SUBMISSIONTYPE, SALESTAXNO, SERVICETAXNO, TIN from AR_CUSTOMER.
    $customerStmt = $dbh->prepare('SELECT CREDITTERM, CURRENCYCODE, AGENT, AREA, SUBMISSIONTYPE, SALESTAXNO, SERVICETAXNO, TIN, TAXEXEMPTNO FROM AR_CUSTOMER WHERE CODE = ?');
    $customerStmt->execute([$customerCode]);
    $customerRow = $customerStmt->fetch(PDO::FETCH_ASSOC);
    if (!$customerRow) {
        throw new Exception('Customer not found for code: ' . $customerCode);
    }
    $terms = trim((string)($customerRow['CREDITTERM'] ?? ''));
    $terms = $terms !== '' ? $terms : 'N/A';
    $customerCurrencyCode = trim((string)($customerRow['CURRENCYCODE'] ?? ''));
    $customerCurrencyCode = $customerCurrencyCode !== '' ? $customerCurrencyCode : 'MYR';
    $customerAgent = trim((string)($customerRow['AGENT'] ?? ''));
    $customerAgent = $customerAgent !== '' ? $customerAgent : '----';
    $customerArea = trim((string)($customerRow['AREA'] ?? ''));
    $customerArea = $customerArea !== '' ? $customerArea : '----';
    $customerSubmissionType = $customerRow['SUBMISSIONTYPE'] ?? null;
    $customerSubmissionType = $customerSubmissionType !== null ? (int)$customerSubmissionType : 17;
    $customerSalesTaxNo = trim((string)($customerRow['SALESTAXNO'] ?? ''));
    $customerServiceTaxNo = trim((string)($customerRow['SERVICETAXNO'] ?? ''));
    $customerTin = trim((string)($customerRow['TIN'] ?? ''));
    $customerTaxExemptNo = trim((string)($customerRow['TAXEXEMPTNO'] ?? ''));

    // Prefer branch values from AR_CUSTOMERBRANCH.
    $branchStmt = $dbh->prepare('SELECT FIRST 1 BRANCHNAME, ADDRESS1, ADDRESS2, ADDRESS3, ADDRESS4, POSTCODE, CITY, STATE, COUNTRY, PHONE1, ATTENTION FROM AR_CUSTOMERBRANCH WHERE CODE = ? ORDER BY DTLKEY');
    $branchStmt->execute([$customerCode]);
    $branchRow = $branchStmt->fetch(PDO::FETCH_ASSOC) ?: [];

    $branchName = trim((string)($branchRow['BRANCHNAME'] ?? ''));
    $branchName = $branchName !== '' ? $branchName : 'BILLING';
    $address1 = trim((string)($branchRow['ADDRESS1'] ?? $address1 ?? ''));
    $address2 = trim((string)($branchRow['ADDRESS2'] ?? $address2 ?? ''));
    $address3 = trim((string)($branchRow['ADDRESS3'] ?? $address3 ?? ''));
    $address4 = trim((string)($branchRow['ADDRESS4'] ?? $address4 ?? ''));
    $postcode = trim((string)($branchRow['POSTCODE'] ?? $postcode ?? ''));
    $city = trim((string)($branchRow['CITY'] ?? $city ?? ''));
    $state = trim((string)($branchRow['STATE'] ?? $state ?? ''));
    $country = trim((string)($branchRow['COUNTRY'] ?? $country ?? ''));
    $phone1 = trim((string)($branchRow['PHONE1'] ?? $phone1 ?? ''));
    $branchAttention = trim((string)($branchRow['ATTENTION'] ?? ''));

    // Resolve currency buying rate from CURRENCY using AR_CUSTOMER.CURRENCYCODE.
    $currencyRateStmt = $dbh->prepare('SELECT FIRST 1 BUYINGRATE FROM CURRENCY WHERE UPPER(CODE) = UPPER(?)');
    $currencyRateStmt->execute([$customerCurrencyCode]);
    $customerCurrencyRate = $currencyRateStmt->fetchColumn();
    $customerCurrencyRate = ($customerCurrencyRate !== false && $customerCurrencyRate !== null)
        ? (float)$customerCurrencyRate
        : 1;
    
    // Get next DOCKEY
    $stmt = $dbh->prepare('SELECT COALESCE(MAX(DOCKEY), 0) + 1 FROM SL_QT');
    $stmt->execute();
    $dockey = $stmt->fetchColumn();
    
    // Generate DOCNO as QT-00001, QT-00002 format (always 5 digits)
    $docNoStmt = $dbh->prepare("SELECT DOCNO FROM SL_QT WHERE DOCNO STARTING WITH 'QT-'");
    $docNoStmt->execute();
    $maxDocNo = 0;
    while ($docNoRow = $docNoStmt->fetch(PDO::FETCH_ASSOC)) {
        $existingDocNo = (string)($docNoRow['DOCNO'] ?? '');
        if (preg_match('/^QT-(\d+)$/', $existingDocNo, $matches)) {
            $docNoNumber = (int)$matches[1];
            if ($docNoNumber > $maxDocNo) {
                $maxDocNo = $docNoNumber;
            }
        }
    }
    $nextDocNo = $maxDocNo + 1;
    $docno = 'QT-' . str_pad($nextDocNo, 5, '0', STR_PAD_LEFT);
    
    // Calculate total amount from items
    $totalAmount = 0;
    foreach ($items as $item) {
        $qty = (float)($item['qty'] ?? 0);
        $unitprice = (float)($item['price'] ?? 0);
        $disc = (float)($item['discount'] ?? 0);
        $totalAmount += applyDiscountAmount($qty, $unitprice, $disc);
    }
    
    $docDate = date('Y-m-d');
    $quotationStatus = 0; // 0 = DRAFT, 1 = COMPLETED
    
    // Insert quotation header into SL_QT
    $qtStmt = $dbh->prepare('
        INSERT INTO SL_QT (
            DOCKEY, DOCNO, DOCDATE, CODE, DESCRIPTION, DOCAMT, 
            CURRENCYCODE, CURRENCYRATE, VALIDITY, SHIPPER, STATUS, IDTYPE, TERMS, AGENT, AREA, COMPANYNAME,
            BRANCHNAME, ADDRESS1, ADDRESS2, ADDRESS3, ADDRESS4, POSTCODE, CITY, STATE, COUNTRY, PHONE1, ATTENTION,
            DADDRESS1, DADDRESS2, DADDRESS3, DADDRESS4, DPOSTCODE, DCITY, DSTATE, DCOUNTRY, DPHONE1, DMOBILE, DFAX1, DATTENTION,
            SALESTAXNO, SERVICETAXNO, TIN, TAXEXEMPTNO, TRANSFERABLE, PRINTCOUNT, SUBMISSIONTYPE, CANCELLED, PROJECT
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            $customerCurrencyCode,
            $customerCurrencyRate,
            $udfValidity, // VALIDITY: user-supplied or today+30
            '----',  // Default shipper
            $quotationStatus,
            1, // IDTYPE default
            $terms,
            $customerAgent,
            $customerArea,
            $companyName,
            $branchName,
            $address1,
            $address2,
            $address3,
            $address4,
            $postcode,
            $city,
            $state,
            $country,
            $phone1,
            $branchAttention,     // ATTENTION from AR_CUSTOMERBRANCH
            $address1,    // DADDRESS1 - same as billing
            $address2,    // DADDRESS2 - same as billing
            $address3,    // DADDRESS3 - same as billing
            $address4,    // DADDRESS4 - same as billing
            $postcode,    // DPOSTCODE - same as billing
            $city,        // DCITY - same as billing
            $state,       // DSTATE - same as billing
            $country,     // DCOUNTRY - same as billing
            $phone1,      // DPHONE1 - same as billing
            null,         // DMOBILE - not provided, set to null
            null,         // DFAX1 - not provided, set to null
            $branchAttention,  // DATTENTION from AR_CUSTOMERBRANCH
            $customerSalesTaxNo,   // SALESTAXNO from AR_CUSTOMER
            $customerServiceTaxNo,  // SERVICETAXNO from AR_CUSTOMER
            $customerTin,   // TIN from AR_CUSTOMER
            $customerTaxExemptNo,  // TAXEXEMPTNO from AR_CUSTOMER
            true,         // SL_QTTRANSFERABLE
            0,            // PRINTCOUNT
            $customerSubmissionType,
            false,        // CANCELLED defaults to FALSE on create
            '----'       // Default PROJECT
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
                UOM, RATE, UNITPRICE, DISC, AMOUNT, UDF_STDPRICE, DELIVERYDATE, IRBM_CLASSIFICATION, PROJECT, LOCATION
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            '022',
            '----',      // Default PROJECT
            '----'       // Default LOCATION
        ]);
        
        $seq++;
    }

    // Move quotation status to COMPLETED (1) once all lines are inserted successfully
    $completeStmt = $dbh->prepare('UPDATE SL_QT SET STATUS = ? WHERE DOCKEY = ?');
    $completeStmt->execute([1, $dockey]); // 1 = COMPLETED

    // If submitted from SL_QTDRAFT edit flow, remove the saved draft rows
    if ($draftDockey !== null && $draftDockey !== '' && is_numeric($draftDockey)) {
        $draftKey = (int)$draftDockey;

        $deleteDraftDtl = $dbh->prepare('DELETE FROM SL_QTDTLDRAFT WHERE DOCKEY = ?');
        $deleteDraftDtl->execute([$draftKey]);

        $deleteDraftHdr = $dbh->prepare('DELETE FROM SL_QTDRAFT WHERE DOCKEY = ?');
        $deleteDraftHdr->execute([$draftKey]);

        error_log("DEBUG: Draft deleted after submission - draftDockey: $draftKey");
    }
    
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



