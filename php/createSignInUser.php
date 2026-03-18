<?php
// createSignInUser.php - Insert guest sign-in payload into AR_CUSTOMER and AR_CUSTOMERBRANCH
header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');

require_once 'db_helper.php';

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    echo json_encode(['success' => true]);
    exit;
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    echo json_encode(['success' => false, 'error' => 'POST method required']);
    exit;
}

$data = json_decode(file_get_contents('php://input'), true);
if (!is_array($data)) {
    echo json_encode(['success' => false, 'error' => 'Invalid JSON payload']);
    exit;
}

$companyName = trim($data['COMPANYNAME'] ?? '');
$area = trim($data['AREA'] ?? '');
$currencyInput = trim($data['CURRENCYCODE'] ?? '');
$udfEmail = trim($data['UDF_EMAIL'] ?? '');
$brn = trim($data['BRN'] ?? '');
$brn2 = trim($data['BRN2'] ?? '');
$tin = trim($data['TIN'] ?? '');
$customerCode = trim($data['CUSTOMERCODE'] ?? '');

$address1 = trim($data['ADDRESS1'] ?? '');
$address2 = trim($data['ADDRESS2'] ?? '');
$address3 = trim($data['ADDRESS3'] ?? '');
$address4 = trim($data['ADDRESS4'] ?? '');
$postcode = trim($data['POSTCODE'] ?? '');
$attention = trim($data['ATTENTION'] ?? '');
$phone1 = trim($data['PHONE1'] ?? '');
$branchName = trim($data['BRANCHNAME'] ?? $companyName);
$branchType = trim($data['BRANCHTYPE'] ?? '');
$city = trim($data['CITY'] ?? '');
$state = trim($data['STATE'] ?? '');
$country = trim($data['COUNTRY'] ?? '');
$phone2 = trim($data['PHONE2'] ?? '');
$mobile = trim($data['MOBILE'] ?? '');
$fax1 = trim($data['FAX1'] ?? '');
$fax2 = trim($data['FAX2'] ?? '');
$branchEmail = trim($data['EMAIL'] ?? $udfEmail);

if ($companyName === '' || $area === '' || $currencyInput === '' || $udfEmail === '' || $brn === '' || $brn2 === '' || $tin === '' || $address1 === '' || $postcode === '' || $attention === '' || $phone1 === '') {
    echo json_encode(['success' => false, 'error' => 'Missing required fields']);
    exit;
}



function generateDTLKEY(PDO $dbh) {
    // Find the next available DTLKEY by checking for existing ones
    $checkStmt = $dbh->prepare('SELECT COUNT(*) FROM AR_CUSTOMERBRANCH WHERE DTLKEY = ?');
    
    for ($i = 1; $i <= 1000000; $i++) {
        $checkStmt->execute([$i]);
        $exists = (int)$checkStmt->fetchColumn();
        if ($exists === 0) {
            return $i;  // Return first available DTLKEY
        }
    }
    throw new Exception('Unable to generate unique DTLKEY');
}

try {
    $dbh = getFirebirdConnection();
    $dbh->beginTransaction();

    // AREA in AR_CUSTOMER must come from AREA.CODE.
    $areaStmt = $dbh->prepare('SELECT FIRST 1 CODE FROM AREA WHERE UPPER(CODE) = UPPER(?)');
    $areaStmt->execute([$area]);
    $areaRow = $areaStmt->fetch(PDO::FETCH_ASSOC);
    $areaCode = $areaRow['CODE'] ?? null;
    if (!$areaCode || trim((string)$areaCode) === '') {
        throw new Exception('Invalid area: ' . $area);
    }
    $areaCode = trim((string)$areaCode);

    // Always store SYMBOL in AR_CUSTOMER.CURRENCYCODE.
    // Accept either SYMBOL or CODE from frontend, then resolve to SYMBOL.
    $currencyStmt = $dbh->prepare('SELECT FIRST 1 SYMBOL FROM CURRENCY WHERE UPPER(SYMBOL) = UPPER(?) OR UPPER(CODE) = UPPER(?)');
    $currencyStmt->execute([$currencyInput, $currencyInput]);
    $currencyRow = $currencyStmt->fetch(PDO::FETCH_ASSOC);
    $currencySymbol = $currencyRow['SYMBOL'] ?? null;
    if (!$currencySymbol || trim((string)$currencySymbol) === '') {
        throw new Exception('Invalid currency: ' . $currencyInput);
    }
    $currencySymbol = trim((string)$currencySymbol);

    // Get or generate customer code
    if (!empty($customerCode)) {
        // Use provided customer code (already validated by backend)
        $code = $customerCode;
    } else {
        // Auto-generate customer code in fixed format: %.3s-%.1s%.4d (e.g., 300-E0888)
        $fixedPrefix = '300';
        $fixedLetter = 'E';

        // Find the next sequence number for the fixed 300-E#### series.
        $maxQuery = $dbh->prepare("SELECT MAX(CAST(SUBSTRING(CODE FROM 6) AS INTEGER)) as maxSeq FROM AR_CUSTOMER WHERE CODE LIKE ?");
        $pattern = $fixedPrefix . '-' . $fixedLetter . '%';
        $maxQuery->execute([$pattern]);
        $result = $maxQuery->fetch(PDO::FETCH_ASSOC);
        $nextSeq = (int)($result['maxSeq'] ?? 0) + 1;

        // Ensure sequence doesn't exceed 4 digits
        if ($nextSeq > 9999) {
            throw new Exception('Maximum customer code sequence reached for ' . $fixedPrefix . '-' . $fixedLetter . '####');
        }

        // Requested template equivalent in PHP with zero-padded 4 digits.
        // If there is a collision, keep incrementing until an unused code is found.
        $checkStmt = $dbh->prepare('SELECT COUNT(*) FROM AR_CUSTOMER WHERE CODE = ?');
        do {
            if ($nextSeq > 9999) {
                throw new Exception('Maximum customer code sequence reached for ' . $fixedPrefix . '-' . $fixedLetter . '####');
            }
            $code = sprintf('%.3s-%.1s%04d', $fixedPrefix, $fixedLetter, $nextSeq);
            $checkStmt->execute([$code]);
            $exists = (int)$checkStmt->fetchColumn();
            $nextSeq++;
        } while ($exists > 0);
    }

    // Apply required defaults for guest sign-in AR_CUSTOMER creation.
    $insertCustomer = $dbh->prepare('        
        INSERT INTO AR_CUSTOMER (
            CODE,
            CONTROLACCOUNT,
            COMPANYNAME,
            COMPANYCATEGORY,
            AREA,
            AGENT,
            CREDITTERM,
            CREDITLIMIT,
            OVERDUELIMIT,
            STATEMENTTYPE,
            CURRENCYCODE,
            OUTSTANDING,
            ALLOWEXCEEDCREDITLIMIT,
            ADDPDCTOCRLIMIT,
            AGINGON,
            STATUS,
            BRN,
            BRN2,
            TIN,
            IDTYPE,
            IDNO,
            CREATIONDATE,
            SUBMISSIONTYPE,
            UDF_EMAIL
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, TRUE, TRUE, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
    ');
    $insertCustomer->execute([
        $code,
        '300-000',
        $companyName,
        '----',
        $areaCode,
        '----',
        '30 Days',
        30000,
        0,
        'O',
        $currencySymbol,
        0,
        'I',
        'P',
        $brn,
        $brn2,
        $tin,
        1,
        $brn2,
        17,
        $udfEmail
    ]);

    $dtlkey = generateDTLKEY($dbh);

    $insertBranch = $dbh->prepare('
        INSERT INTO AR_CUSTOMERBRANCH (
            DTLKEY,
            CODE,
            BRANCHTYPE,
            BRANCHNAME,
            ADDRESS1,
            ADDRESS2,
            ADDRESS3,
            ADDRESS4,
            POSTCODE,
            CITY,
            STATE,
            COUNTRY,
            ATTENTION,
            PHONE1,
            PHONE2,
            MOBILE,
            FAX1,
            FAX2,
            EMAIL
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ');
    $insertBranch->execute([
        $dtlkey,
        $code,
        $branchType,
        $branchName,
        $address1,
        $address2,
        $address3,
        $address4,
        $postcode,
        $city,
        $state,
        $country,
        $attention,
        $phone1,
        $phone2,
        $mobile,
        $fax1,
        $fax2,
        $branchEmail
    ]);

    $dbh->commit();

    echo json_encode([
        'success' => true,
        'message' => 'Guest sign-in user created successfully',
        'customerCode' => $code
    ]);
} catch (Exception $e) {
    if (isset($dbh) && $dbh->inTransaction()) {
        $dbh->rollBack();
    }
    error_log('createSignInUser.php error: ' . $e->getMessage());
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}
?>
