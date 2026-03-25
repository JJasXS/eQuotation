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
    // Check if it's multipart/form-data or has POST data
    if (!empty($_POST)) {
        $data = $_POST;
    } elseif ($_SERVER['CONTENT_TYPE'] && strpos($_SERVER['CONTENT_TYPE'], 'multipart/form-data') !== false) {
        $data = $_POST;
    } else {
        echo json_encode(['success' => false, 'error' => 'Invalid JSON payload']);
        exit;
    }
}

$companyName = trim($data['COMPANYNAME'] ?? '');
$area = trim($data['AREA'] ?? '');
$currencyInput = trim($data['CURRENCYCODE'] ?? '');
$udfEmail = trim($data['UDF_EMAIL'] ?? '');
$brn = trim($data['BRN'] ?? '');
$brn2 = trim($data['BRN2'] ?? '');
$tin = trim($data['TIN'] ?? '');
$salesTaxNo = trim($data['SALESTAXNO'] ?? '');
$serviceTaxNo = trim($data['SERVICETAXNO'] ?? '');
$taxExemptNo = trim($data['TAXEXEMPTNO'] ?? '');
$taxExpDateRaw = trim($data['TAXEXPDATE'] ?? '');
$taxExpDate = $taxExpDateRaw === '' ? null : $taxExpDateRaw;

$address1 = trim($data['ADDRESS1'] ?? '');
$address2 = trim($data['ADDRESS2'] ?? '');
$address3 = trim($data['ADDRESS3'] ?? '');
$address4 = trim($data['ADDRESS4'] ?? '');
$postcode = trim($data['POSTCODE'] ?? '');
$attention = trim($data['ATTENTION'] ?? '');
$phone1 = trim($data['PHONE1'] ?? '');
// BRANCHNAME / BRANCHTYPE are enforced by DB trigger (e.g. BRANCHTYPE='B' => BRANCHNAME='BILLING').
// Keep payload values optional; let database decide defaults.
$branchName = trim($data['BRANCHNAME'] ?? '');
$branchType = trim($data['BRANCHTYPE'] ?? '');
// Set defaults if empty to ensure SQL Account compatibility
if ($branchType === '') {
    $branchType = 'B';
}
if ($branchName === '') {
    $branchName = 'BILLING';
}
$city = trim($data['CITY'] ?? '');
$state = trim($data['STATE'] ?? '');
$country = trim($data['COUNTRY'] ?? '');
$phone2 = trim($data['PHONE2'] ?? '');
$mobile = trim($data['MOBILE'] ?? '');
$fax1 = trim($data['FAX1'] ?? '');
$fax2 = trim($data['FAX2'] ?? '');
$branchEmail = trim($data['EMAIL'] ?? $udfEmail);
$attachments = trim($data['ATTACHMENTS'] ?? '');

if ($companyName === '' || $area === '' || $currencyInput === '' || $udfEmail === '' || $brn === '' || $brn2 === '' || $tin === '' || $address1 === '' || $postcode === '' || $attention === '' || $phone1 === '' || $branchType === '' || $branchName === '') {
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

    // Always store CODE in AR_CUSTOMER.CURRENCYCODE.
    // Accept either CODE or SYMBOL from frontend, then resolve to CODE.
    $currencyStmt = $dbh->prepare('SELECT FIRST 1 CODE FROM CURRENCY WHERE UPPER(CODE) = UPPER(?) OR UPPER(SYMBOL) = UPPER(?)');
    $currencyStmt->execute([$currencyInput, $currencyInput]);
    $currencyRow = $currencyStmt->fetch(PDO::FETCH_ASSOC);
    $currencyCode = $currencyRow['CODE'] ?? null;
    if (!$currencyCode || trim((string)$currencyCode) === '') {
        throw new Exception('Invalid currency: ' . $currencyInput);
    }
    $currencyCode = trim((string)$currencyCode);

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

    // Keep incrementing until an unused code is found.
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

    // Handle file uploads for attachments
    $attachmentsDir = '';
    if (isset($_FILES['ATTACHMENTS']) && is_array($_FILES['ATTACHMENTS']['name'])) {
        $uploadDir = __DIR__ . '/../uploads/customers/' . $code . '/';
        if (!is_dir($uploadDir)) {
            mkdir($uploadDir, 0755, true);
        }
        $attachmentsDir = 'uploads/customers/' . $code . '/'; // Store relative path

        foreach ($_FILES['ATTACHMENTS']['name'] as $key => $name) {
            if ($_FILES['ATTACHMENTS']['error'][$key] === UPLOAD_ERR_OK) {
                $tmpName = $_FILES['ATTACHMENTS']['tmp_name'][$key];
                $safeName = preg_replace('/[^a-zA-Z0-9._-]/', '_', $name);
                move_uploaded_file($tmpName, $uploadDir . $safeName);
            }
        }
    }
    $attachments = $attachmentsDir;

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
            SALESTAXNO,
            SERVICETAXNO,
            TAXEXEMPTNO,
            TAXEXPDATE,
            IDTYPE,
            IDNO,
            CREATIONDATE,
            SUBMISSIONTYPE,
            UDF_EMAIL,
            ATTACHMENTS
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, TRUE, TRUE, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?)
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
        $currencyCode,
        0,
        'I',      // AGINGON (FIXED: should be 'I' not 'P')
        'P',      // STATUS: P for Prospect/Pending (FIXED: should be 'P' not 'A')
        $brn, $brn2, $tin, $salesTaxNo, $serviceTaxNo, $taxExemptNo, $taxExpDate, 1, $brn2, 17, $udfEmail, $attachments
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
