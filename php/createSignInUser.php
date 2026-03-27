<?php
// createSignInUser.php - Create guest sign-in customer through FastAPI COM middleware only
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

function envOrDefault(string $name, string $default): string
{
    $value = getenv($name);
    if ($value === false || trim($value) === '') {
        return $default;
    }
    return trim($value);
}

function formatTaxDate(?string $value): ?string
{
    $value = trim((string)$value);
    if ($value === '') {
        return null;
    }
    $ts = strtotime($value);
    if ($ts === false) {
        return null;
    }
    return date('Y-m-d', $ts);
}

function generateCustomerCode(PDO $dbh): string
{
    $fixedPrefix = '300';
    $fixedLetter = 'E';
    $pattern = $fixedPrefix . '-' . $fixedLetter . '%';

    $maxQuery = $dbh->prepare("SELECT MAX(CAST(SUBSTRING(CODE FROM 6) AS INTEGER)) as maxSeq FROM AR_CUSTOMER WHERE CODE LIKE ?");
    $maxQuery->execute([$pattern]);
    $result = $maxQuery->fetch(PDO::FETCH_ASSOC);
    $nextSeq = (int)($result['maxSeq'] ?? 0) + 1;

    $checkStmt = $dbh->prepare('SELECT COUNT(*) FROM AR_CUSTOMER WHERE CODE = ?');
    for ($i = 0; $i < 5000; $i++) {
        if ($nextSeq > 9999) {
            throw new Exception('Maximum customer code sequence reached for 300-E####');
        }
        $code = sprintf('%.3s-%.1s%04d', $fixedPrefix, $fixedLetter, $nextSeq);
        $checkStmt->execute([$code]);
        $exists = (int)$checkStmt->fetchColumn();
        if ($exists === 0) {
            return $code;
        }
        $nextSeq++;
    }

    throw new Exception('Unable to generate unique customer code');
}

function generateBranchDtlKey(PDO $dbh): string
{
    $stmt = $dbh->query('SELECT COALESCE(MAX(DTLKEY), 0) AS max_dtlkey FROM AR_CUSTOMERBRANCH');
    $row = $stmt ? $stmt->fetch(PDO::FETCH_ASSOC) : null;
    $next = ((int)($row['MAX_DTLKEY'] ?? $row['max_dtlkey'] ?? 0)) + 1;
    return (string)$next;
}

$area = trim($data['AREA'] ?? '');
$currencyInput = trim($data['CURRENCYCODE'] ?? '');
$companyName = trim($data['COMPANYNAME'] ?? '');
$udfEmail = trim($data['UDF_EMAIL'] ?? '');
$brn = trim($data['BRN'] ?? '');
$brn2 = trim($data['BRN2'] ?? '');
$tin = trim($data['TIN'] ?? '');
$salesTaxNo = trim($data['SALESTAXNO'] ?? '');
$serviceTaxNo = trim($data['SERVICETAXNO'] ?? '');
$taxExemptNo = trim($data['TAXEXEMPTNO'] ?? '');
$taxExpDate = formatTaxDate($data['TAXEXPDATE'] ?? null);
$attachments = trim($data['ATTACHMENTS'] ?? '');
$phone1 = trim($data['PHONE1'] ?? '');
$phone2 = trim($data['PHONE2'] ?? '');
$mobile = trim($data['MOBILE'] ?? '');
$fax1 = trim($data['FAX1'] ?? '');
$fax2 = trim($data['FAX2'] ?? '');
$branchEmail = trim($data['EMAIL'] ?? $udfEmail);
$branchType = trim($data['BRANCHTYPE'] ?? 'B');
$branchName = trim($data['BRANCHNAME'] ?? 'BILLING');
$attention = trim($data['ATTENTION'] ?? '');
$address1 = trim($data['ADDRESS1'] ?? '');
$address2 = trim($data['ADDRESS2'] ?? '');
$address3 = trim($data['ADDRESS3'] ?? '');
$address4 = trim($data['ADDRESS4'] ?? '');
$postcode = trim($data['POSTCODE'] ?? '');
$city = trim($data['CITY'] ?? '');
$state = trim($data['STATE'] ?? '');
$country = trim($data['COUNTRY'] ?? '');
$creditTerm = trim((string)($data['CREDITTERM'] ?? '30'));

if ($companyName === '' || $phone1 === '' || $address1 === '' || $area === '' || $currencyInput === '' || $udfEmail === '' || $brn === '') {
    echo json_encode([
        'success' => false,
        'error' => 'Missing required fields: COMPANYNAME, PHONE1, ADDRESS1, AREA, CURRENCYCODE, UDF_EMAIL, BRN'
    ]);
    exit;
}

try {
    $dbh = getFirebirdConnection();

    $areaStmt = $dbh->prepare('SELECT FIRST 1 CODE FROM AREA WHERE UPPER(CODE) = UPPER(?)');
    $areaStmt->execute([$area]);
    $areaRow = $areaStmt->fetch(PDO::FETCH_ASSOC);
    $areaCode = trim((string)($areaRow['CODE'] ?? ''));
    if ($areaCode === '') {
        throw new Exception('Invalid AREA: ' . $area);
    }

    $currencyStmt = $dbh->prepare(
        'SELECT FIRST 1 CODE FROM CURRENCY WHERE UPPER(CODE) = UPPER(?) OR UPPER(SYMBOL) = UPPER(?)'
    );
    $currencyStmt->execute([$currencyInput, $currencyInput]);
    $currencyRow = $currencyStmt->fetch(PDO::FETCH_ASSOC);
    $currencyCode = trim((string)($currencyRow['CODE'] ?? ''));
    if ($currencyCode === '') {
        throw new Exception('Invalid CURRENCYCODE: ' . $currencyInput);
    }

    $customerCode = generateCustomerCode($dbh);
    $branchDtlKey = generateBranchDtlKey($dbh);
} catch (Exception $e) {
    error_log('createSignInUser.php lookup/generation error: ' . $e->getMessage());
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
    exit;
}

$apiBaseUrl = rtrim(envOrDefault('FASTAPI_BASE_URL', 'http://127.0.0.1:8000'), '/');
$customersUrl = $apiBaseUrl . '/customers';

$payload = [
    'code' => $customerCode,
    'company_name' => $companyName,
    'credit_term' => $creditTerm !== '' ? $creditTerm : '30 Days',
    'control_account' => '300-000',
    'company_category' => '----',
    'area' => $areaCode,
    'agent' => '----',
    'statement_type' => 'O',
    'currency_code' => $currencyCode,
    'aging_on' => 'I',
    'status' => 'A',
    'submission_type' => null,
    'brn' => $brn,
    'brn2' => $brn2 !== '' ? $brn2 : null,
    'tin' => $tin !== '' ? $tin : null,
    'sales_tax_no' => $salesTaxNo !== '' ? $salesTaxNo : null,
    'service_tax_no' => $serviceTaxNo !== '' ? $serviceTaxNo : null,
    'tax_exempt_no' => $taxExemptNo !== '' ? $taxExemptNo : null,
    'tax_exp_date' => $taxExpDate,
    'udf_email' => $udfEmail,
    'attachments' => $attachments !== '' ? $attachments : null,
    'phone' => $phone1,
    'phone2' => $phone2 !== '' ? $phone2 : null,
    'mobile' => $mobile !== '' ? $mobile : null,
    'fax1' => $fax1 !== '' ? $fax1 : null,
    'fax2' => $fax2 !== '' ? $fax2 : null,
    'email' => $branchEmail !== '' ? $branchEmail : $udfEmail,
    'branch_type' => $branchType !== '' ? $branchType : 'B',
    'branch_name' => $branchName !== '' ? $branchName : 'BILLING',
    'branch_dtlkey' => $branchDtlKey,
    'attention' => $attention !== '' ? $attention : null,
    'address1' => $address1,
    'address2' => $address2 !== '' ? $address2 : null,
    'address3' => $address3 !== '' ? $address3 : null,
    'address4' => $address4 !== '' ? $address4 : null,
    'postcode' => $postcode !== '' ? $postcode : null,
    'city' => $city !== '' ? $city : null,
    'state' => $state !== '' ? $state : null,
    'country' => $country !== '' ? $country : null,
];
$ch = curl_init($customersUrl);
curl_setopt_array($ch, [
    CURLOPT_POST => true,
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_HTTPHEADER => ['Content-Type: application/json'],
    CURLOPT_POSTFIELDS => json_encode($payload),
    CURLOPT_CONNECTTIMEOUT => 10,
    CURLOPT_TIMEOUT => 30,
]);

$responseBody = curl_exec($ch);
$curlError = curl_error($ch);
$httpCode = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);

if ($responseBody === false) {
    error_log('createSignInUser.php cURL error: ' . $curlError);
    echo json_encode([
        'success' => false,
        'error' => 'Failed to connect to COM middleware',
        'details' => $curlError
    ]);
    exit;
}

$responseJson = json_decode($responseBody, true);
if (!is_array($responseJson)) {
    error_log('createSignInUser.php invalid middleware response: ' . $responseBody);
    echo json_encode([
        'success' => false,
        'error' => 'Invalid response from COM middleware',
        'httpCode' => $httpCode
    ]);
    exit;
}

if ($httpCode >= 200 && $httpCode < 300 && !empty($responseJson['success'])) {
    $createdCode = $responseJson['data']['customer']['code']
        ?? $responseJson['data']['code']
        ?? $customerCode;
    echo json_encode([
        'success' => true,
        'message' => 'Guest sign-in user created successfully',
        'customerCode' => $createdCode,
        'postCreateState' => $responseJson['data']['post_create_state'] ?? null,
        'middleware' => [
            'status' => $httpCode,
            'message' => $responseJson['message'] ?? null
        ]
    ]);
    exit;
}

$errorMessage = $responseJson['detail']
    ?? $responseJson['message']
    ?? $responseJson['error']
    ?? 'Customer creation rejected by COM middleware';

error_log('createSignInUser.php middleware error: HTTP ' . $httpCode . ' ' . $errorMessage);
echo json_encode([
    'success' => false,
    'error' => $errorMessage,
    'middleware' => [
        'status' => $httpCode,
        'response' => $responseJson
    ]
]);
exit;

?>
