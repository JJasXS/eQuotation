<?php
// insertDraftQuotation.php - Create a draft quotation in SL_QT (NULL CANCELLED acts as DRAFT)
header('Content-Type: application/json');
require_once 'db_helper.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    echo json_encode(['success' => false, 'error' => 'POST method required']);
    exit;
}

$data = json_decode(file_get_contents('php://input'), true);
$customerCode = $data['customerCode'] ?? null;
$chatId = $data['chatId'] ?? null;
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

if (!$customerCode) {
    echo json_encode(['success' => false, 'error' => 'customerCode required']);
    exit;
}

try {
    $dbh = getFirebirdConnection();
    
    // Check if there's already a draft quotation (CANCELLED = NULL) for this customer/chat
    if ($chatId) {
        $checkStmt = $dbh->prepare('SELECT FIRST 1 DOCKEY FROM SL_QT WHERE CODE = ? AND CANCELLED IS NULL');
        $checkStmt->execute([$customerCode]);
        $existing = $checkStmt->fetch(PDO::FETCH_ASSOC);
        
        if ($existing) {
            // Return existing draft quotation
            echo json_encode([
                'success' => true,
                'dockey' => $existing['DOCKEY'],
                'message' => 'Using existing draft quotation'
            ]);
            exit;
        }
    }
    
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
    
    $docDate = date('Y-m-d');
    
    // Fetch CREDITTERM from AR_CUSTOMER
    $termsStmt = $dbh->prepare('SELECT CREDITTERM FROM AR_CUSTOMER WHERE CODE = ?');
    $termsStmt->execute([$customerCode]);
    $terms = $termsStmt->fetchColumn();
    $terms = $terms ?: 'N/A';

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
    
    // Insert draft quotation header into SL_QT with CANCELLED = NULL (acts as DRAFT)
    $qtStmt = $dbh->prepare('
        INSERT INTO SL_QT (
            DOCKEY, DOCNO, DOCDATE, CODE, DESCRIPTION, DOCAMT, 
            CURRENCYCODE, VALIDITY, SHIPPER, STATUS, IDTYPE, TERMS, COMPANYNAME,
            ADDRESS1, ADDRESS2, ADDRESS3, ADDRESS4, POSTCODE, CITY, STATE, COUNTRY, PHONE1, CANCELLED, PROJECT
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ');
    $qtStmt->execute([
        $dockey,
        $docno,
        $docDate,
        $customerCode,
        'Draft Quotation',  // Default description
        0,                   // Initial amount = 0
        'MYR',              // Default currency
        null,               // No validity set yet
        'AUTO',             // Default shipper
        0,                  // STATUS = 0 (DRAFT)
        1,                  // IDTYPE default
        $terms,             // Credit terms
        $companyName,       // Company name
        $address1,          // Address 1
        $address2,          // Address 2
        $address3,          // Address 3
        $address4,          // Address 4
        $postcode,          // Postcode
        $city,              // City
        $state,             // State
        $country,           // Country
        $phone1,            // Phone
        null,               // CANCELLED = NULL (acts as DRAFT indicator)
        '----'              // Default PROJECT
    ]);
    
    echo json_encode([
        'success' => true,
        'dockey' => $dockey,
        'docno' => $docno,
        'message' => 'Draft quotation created successfully'
    ]);

} catch (Exception $e) {
    error_log("insertDraftQuotation.php error: " . $e->getMessage());
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}
?>
