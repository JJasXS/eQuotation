<?php
// saveDraftQuotation.php - Save quotation drafts into SL_QTDRAFT/SL_QTDTLDRAFT
header('Content-Type: application/json');
require_once 'db_helper.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    echo json_encode(['success' => false, 'error' => 'POST method required']);
    exit;
}

$data = json_decode(file_get_contents('php://input'), true);
$customerCode = $data['customerCode'] ?? null;
$dockey = $data['dockey'] ?? null;
$description = trim($data['description'] ?? 'Draft Quotation');
$validUntil = $data['validUntil'] ?? null;
$currencyCode = $data['currencyCode'] ?? 'MYR';
$companyName = $data['companyName'] ?? null;
$address1 = $data['address1'] ?? null;
$address2 = $data['address2'] ?? null;
$phone1 = $data['phone1'] ?? null;
$items = $data['items'] ?? [];

if (!$customerCode) {
    echo json_encode(['success' => false, 'error' => 'customerCode required']);
    exit;
}

$validityDate = (!empty($validUntil) && $validUntil !== '') ? $validUntil : date('Y-m-d', strtotime('+30 days'));

function applyDiscountAmount(float $qty, float $unitprice, float $discAmount): float {
    $lineSubtotal = $qty * $unitprice;
    if ($discAmount <= 0) {
        return max(0, $lineSubtotal);
    }
    return max(0, $lineSubtotal - $discAmount);
}

try {
    $dbh = getFirebirdConnection();
    $dbh->beginTransaction();

    $termsStmt = $dbh->prepare('SELECT CREDITTERM FROM AR_CUSTOMER WHERE CODE = ?');
    $termsStmt->execute([$customerCode]);
    $terms = $termsStmt->fetchColumn();
    $terms = $terms ?: 'N/A';

    $totalAmount = 0;
    foreach ($items as $item) {
        $product = trim((string)($item['product'] ?? ''));
        $qty = (float)($item['qty'] ?? 0);
        $unitprice = (float)($item['price'] ?? 0);
        $disc = (float)($item['discount'] ?? 0);
        if ($product !== '' && $qty > 0 && $unitprice >= 0) {
            $totalAmount += applyDiscountAmount($qty, $unitprice, $disc);
        }
    }

    $docDate = date('Y-m-d');
    $docno = null;

    if (!empty($dockey)) {
        $existingStmt = $dbh->prepare('SELECT DOCKEY, DOCNO FROM SL_QTDRAFT WHERE DOCKEY = ? AND CODE = ?');
        $existingStmt->execute([(int)$dockey, $customerCode]);
        $existing = $existingStmt->fetch(PDO::FETCH_ASSOC);

        if ($existing) {
            $docno = $existing['DOCNO'];
            $updateStmt = $dbh->prepare('
                UPDATE SL_QTDRAFT
                SET DESCRIPTION = ?,
                    VALIDITY = ?,
                    DOCAMT = ?,
                    COMPANYNAME = ?,
                    ADDRESS1 = ?,
                    ADDRESS2 = ?,
                    PHONE1 = ?,
                    TERMS = ?,
                    CURRENCYCODE = ?,
                    CANCELLED = ?,
                    STATUS = ?
                WHERE DOCKEY = ?
            ');
            $updateStmt->execute([
                $description,
                $validityDate,
                $totalAmount,
                $companyName,
                $address1,
                $address2,
                $phone1,
                $terms,
                $currencyCode,
                null,
                0,
                (int)$dockey
            ]);
        } else {
            $dockey = null;
        }
    }

    if (empty($dockey)) {
        $nextDockeyStmt = $dbh->prepare('SELECT COALESCE(MAX(DOCKEY), 0) + 1 FROM SL_QTDRAFT');
        $nextDockeyStmt->execute();
        $dockey = (int)$nextDockeyStmt->fetchColumn();

        $docNoStmt = $dbh->prepare("SELECT MAX(CAST(SUBSTRING(DOCNO FROM 5) AS INTEGER)) AS MAXNO FROM SL_QTDRAFT WHERE DOCNO STARTING WITH 'QTD-'");
        $docNoStmt->execute();
        $maxDocNo = $docNoStmt->fetchColumn();
        $nextDocNo = ($maxDocNo !== null && $maxDocNo !== false) ? ((int)$maxDocNo + 1) : 1;
        $docno = 'QTD-' . str_pad($nextDocNo, 4, '0', STR_PAD_LEFT);

        $insertStmt = $dbh->prepare('
            INSERT INTO SL_QTDRAFT (
                DOCKEY, DOCNO, DOCDATE, CODE, DESCRIPTION, DOCAMT,
                CURRENCYCODE, VALIDITY, SHIPPER, STATUS, TERMS,
                COMPANYNAME, ADDRESS1, ADDRESS2, PHONE1, CANCELLED, PROJECT, UDF_VALIDITY
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ');
        $insertStmt->execute([
            $dockey,
            $docno,
            $docDate,
            $customerCode,
            $description,
            $totalAmount,
            $currencyCode,
            $validityDate,
            'AUTO',
            0,
            $terms,
            $companyName,
            $address1,
            $address2,
            $phone1,
            null,
            '----',
            $validityDate
        ]);
    }

    $deleteDetailStmt = $dbh->prepare('DELETE FROM SL_QTDTLDRAFT WHERE DOCKEY = ?');
    $deleteDetailStmt->execute([(int)$dockey]);

    $seq = 1;
    foreach ($items as $item) {
        $product = trim((string)($item['product'] ?? ''));
        $qty = (float)($item['qty'] ?? 0);
        $unitprice = (float)($item['price'] ?? 0);
        $disc = (float)($item['discount'] ?? 0);
        $deliveryDate = !empty($item['deliveryDate']) ? $item['deliveryDate'] : date('Y-m-d');

        if ($product === '' || $qty <= 0 || $unitprice < 0) {
            continue;
        }

        $amount = applyDiscountAmount($qty, $unitprice, $disc);

        $dtlStmt = $dbh->prepare('SELECT COALESCE(MAX(DTLKEY), 0) + 1 FROM SL_QTDTLDRAFT');
        $dtlStmt->execute();
        $dtlkey = (int)$dtlStmt->fetchColumn();

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

        if (!$itemCode) {
            $itemCode = mb_substr($product, 0, 120, 'UTF-8');
        }

        $itemDescription = mb_substr($product, 0, 800, 'UTF-8');

        $detailInsert = $dbh->prepare('
            INSERT INTO SL_QTDTLDRAFT (
                DTLKEY, DOCKEY, SEQ, ITEMCODE, DESCRIPTION, QTY,
                UNITPRICE, DISC, AMOUNT, UDF_STDPRICE, DELIVERYDATE
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ');
        $detailInsert->execute([
            $dtlkey,
            (int)$dockey,
            $seq,
            $itemCode,
            $itemDescription,
            $qty,
            $unitprice,
            (string)$disc,
            $amount,
            null,
            $deliveryDate
        ]);

        $seq++;
    }

    $dbh->commit();

    echo json_encode([
        'success' => true,
        'dockey' => (int)$dockey,
        'docno' => $docno,
        'message' => 'Draft quotation saved successfully'
    ]);
} catch (Exception $e) {
    if (isset($dbh) && $dbh->inTransaction()) {
        $dbh->rollBack();
    }
    error_log('saveDraftQuotation.php error: ' . $e->getMessage());
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}
?>
