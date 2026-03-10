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

$address1 = trim($data['ADDRESS1'] ?? '');
$address2 = trim($data['ADDRESS2'] ?? '');
$address3 = trim($data['ADDRESS3'] ?? '');
$address4 = trim($data['ADDRESS4'] ?? '');
$postcode = trim($data['POSTCODE'] ?? '');
$attention = trim($data['ATTENTION'] ?? '');
$phone1 = trim($data['PHONE1'] ?? '');

if ($companyName === '' || $area === '' || $currencyInput === '' || $udfEmail === '' || $brn === '' || $brn2 === '' || $tin === '' || $address1 === '' || $postcode === '' || $attention === '' || $phone1 === '') {
    echo json_encode(['success' => false, 'error' => 'Missing required fields']);
    exit;
}

function generateGuestCustomerCode(PDO $dbh) {
    // Find max SIG-#### code
    $stmt = $dbh->prepare("SELECT MAX(CODE) AS max_code FROM AR_CUSTOMER WHERE CODE LIKE 'SIG-%'");
    $stmt->execute();
    $row = $stmt->fetch(PDO::FETCH_ASSOC);
    $maxCode = $row['max_code'] ?? '';

    if (preg_match('/SIG-(\d{4})/', $maxCode, $matches)) {
        $nextNum = (int)$matches[1] + 1;
    } else {
        $nextNum = 1;
    }
    $newCode = sprintf('SIG-%04d', $nextNum);

    // Double-check uniqueness (should not be needed, but safe)
    $checkStmt = $dbh->prepare('SELECT COUNT(*) FROM AR_CUSTOMER WHERE CODE = ?');
    $checkStmt->execute([$newCode]);
    $exists = (int)$checkStmt->fetchColumn();
    if ($exists === 0) {
        return $newCode;
    }
    // If collision, try next numbers up to 10 times
    for ($i = 1; $i <= 10; $i++) {
        $tryCode = sprintf('SIG-%04d', $nextNum + $i);
        $checkStmt->execute([$tryCode]);
        $exists = (int)$checkStmt->fetchColumn();
        if ($exists === 0) {
            return $tryCode;
        }
    }
    throw new Exception('Unable to generate unique SIG-#### customer code');
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

    $customerCode = generateGuestCustomerCode($dbh);

    // AR_CUSTOMER.STATUS appears to be CHAR(1), so use code 'P' for Prospect.
    $insertCustomer = $dbh->prepare('        
        INSERT INTO AR_CUSTOMER (CODE, COMPANYNAME, AREA, CURRENCYCODE, UDF_EMAIL, BRN, BRN2, TIN, STATUS, CREATIONDATE)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ');
    $insertCustomer->execute([$customerCode, $companyName, $areaCode, $currencySymbol, $udfEmail, $brn, $brn2, $tin, 'P']);

    $dtlkey = generateDTLKEY($dbh);

    $insertBranch = $dbh->prepare('
        INSERT INTO AR_CUSTOMERBRANCH (DTLKEY, CODE, ADDRESS1, ADDRESS2, ADDRESS3, ADDRESS4, POSTCODE, ATTENTION, PHONE1)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ');
    $insertBranch->execute([$dtlkey, $customerCode, $address1, $address2, $address3, $address4, $postcode, $attention, $phone1]);

    $dbh->commit();

    echo json_encode([
        'success' => true,
        'message' => 'Guest sign-in user created successfully',
        'customerCode' => $customerCode
    ]);
} catch (Exception $e) {
    if (isset($dbh) && $dbh->inTransaction()) {
        $dbh->rollBack();
    }
    error_log('createSignInUser.php error: ' . $e->getMessage());
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}
?>
