<?php
// Test script to create a customer using the corrected INSERT logic
// This will help verify the fix works

require_once 'db_helper.php';

function testCustomerCreation() {
    try {
        $dbh = getDBConnection();

        // Generate test data
        $code = 'TEST-' . date('Ymd-His');
        $companyName = 'Test Company ' . date('His');
        $areaCode = 'KL';
        $brn = 'TEST123456789';
        $udfEmail = 'test@example.com';
        $attachments = '';

        // Use the CORRECTED INSERT logic
        $insertCustomer = $dbh->prepare('
            INSERT INTO AR_CUSTOMER (
                CODE, CONTROLACCOUNT, COMPANYNAME, COMPANYCATEGORY, AREA, AGENT,
                CREDITTERM, CREDITLIMIT, OVERDUELIMIT, STATEMENTTYPE, CURRENCYCODE,
                OUTSTANDING, ALLOWEXCEEDCREDITLIMIT, ADDPDCTOCRLIMIT, AGINGON, STATUS,
                BRN, BRN2, TIN, SALESTAXNO, SERVICETAXNO, TAXEXEMPTNO, TAXEXPDATE,
                IDTYPE, IDNO, CREATIONDATE, SUBMISSIONTYPE, UDF_EMAIL, ATTACHMENTS
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, TRUE, TRUE, ?, ?, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, CURRENT_TIMESTAMP, NULL, ?, ?)
        ');

        $insertCustomer->execute([
            $code,              // CODE
            '300-000',          // CONTROLACCOUNT
            $companyName,       // COMPANYNAME
            '----',             // COMPANYCATEGORY (default)
            $areaCode,          // AREA
            '----',             // AGENT (default)
            '30 Days',          // CREDITTERM
            30000,              // CREDITLIMIT
            0,                  // OVERDUELIMIT
            'O',                // STATEMENTTYPE
            '----',             // CURRENCYCODE (empty!)
            0,                  // OUTSTANDING
            'I',                // AGINGON
            'A',                // STATUS (Active!)
            $brn,               // BRN
            $udfEmail,          // UDF_EMAIL
            $attachments        // ATTACHMENTS
        ]);

        // Generate DTLKEY for branch
        $dtlkey = generateDTLKEY($dbh);

        // Insert branch record
        $insertBranch = $dbh->prepare('
            INSERT INTO AR_CUSTOMERBRANCH (
                DTLKEY, CODE, BRANCHTYPE, BRANCHNAME, ADDRESS1, ADDRESS2, ADDRESS3, ADDRESS4,
                POSTCODE, CITY, STATE, COUNTRY, ATTENTION, PHONE1, PHONE2, MOBILE, FAX1, FAX2, EMAIL
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ');

        $insertBranch->execute([
            $dtlkey,
            $code,
            'B',                // BRANCHTYPE
            'BILLING',          // BRANCHNAME
            'Test Address 1',   // ADDRESS1
            'Test Address 2',   // ADDRESS2
            'Test Address 3',   // ADDRESS3
            'Test Address 4',   // ADDRESS4
            '50000',            // POSTCODE
            'Kuala Lumpur',     // CITY
            'WP Kuala Lumpur',  // STATE
            'Malaysia',         // COUNTRY
            'Test Contact',     // ATTENTION
            '03-12345678',      // PHONE1
            '',                 // PHONE2
            '012-3456789',      // MOBILE
            '',                 // FAX1
            '',                 // FAX2
            $udfEmail           // EMAIL
        ]);

        echo "✅ SUCCESS: Customer created with CODE: $code\n";
        echo "📧 Email: $udfEmail\n";
        echo "🏢 Company: $companyName\n";
        echo "\n🔍 TEST INSTRUCTIONS:\n";
        echo "1. Open SQL Account\n";
        echo "2. Go to AR > Customer Maintenance\n";
        echo "3. Search for customer code: $code\n";
        echo "4. Try to EDIT and SAVE the customer\n";
        echo "5. If it works, the fix is successful!\n";

        return $code;

    } catch (Exception $e) {
        echo "❌ ERROR: " . $e->getMessage() . "\n";
        return false;
    }
}

// Run the test
echo "🧪 TESTING CORRECTED CUSTOMER INSERT LOGIC\n";
echo "==========================================\n\n";

$testCode = testCustomerCreation();

if ($testCode) {
    echo "\n📋 VERIFICATION QUERY:\n";
    echo "SELECT CODE, STATUS, CURRENCYCODE, AGENT, BRN2, IDTYPE, IDNO, SUBMISSIONTYPE\n";
    echo "FROM AR_CUSTOMER WHERE CODE = '$testCode';\n\n";

    echo "Compare with working customer:\n";
    echo "SELECT CODE, STATUS, CURRENCYCODE, AGENT, BRN2, IDTYPE, IDNO, SUBMISSIONTYPE\n";
    echo "FROM AR_CUSTOMER WHERE CODE = '300-D0001';\n";
}
?>