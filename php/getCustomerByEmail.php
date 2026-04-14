<?php
// getCustomerByEmail.php - Get customer details (code, company name, phone, address, credit terms) by email
// Combines lookup by email with full customer info from AR_CUSTOMER and AR_CUSTOMERBRANCH
require_once 'db_helper.php';

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');

$email = $_GET['email'] ?? null;

if (!$email) {
    echo json_encode(['success' => false, 'error' => 'email parameter required']);
    exit;
}

$email = trim($email);

try {
    $con = getFirebirdConnection();
    
    // First check AR_CUSTOMERBRANCH for email using case/space-insensitive match
    $query = 'SELECT CODE FROM AR_CUSTOMERBRANCH WHERE UPPER(TRIM(EMAIL)) = UPPER(TRIM(?))';
    $stmt = $con->prepare($query);
    $stmt->execute([$email]);
    $result = $stmt->fetch(PDO::FETCH_ASSOC);
    
    $customerCode = null;
    if ($result) {
        $customerCode = $result['CODE'];
    } else {
        // If not found in AR_CUSTOMERBRANCH, check AR_CUSTOMER.UDF_EMAIL
        try {
            $query2 = 'SELECT CODE FROM AR_CUSTOMER WHERE UPPER(TRIM(UDF_EMAIL)) = UPPER(TRIM(?))';
            $stmt2 = $con->prepare($query2);
            $stmt2->execute([$email]);
            $result2 = $stmt2->fetch(PDO::FETCH_ASSOC);
            if ($result2) {
                $customerCode = $result2['CODE'];
            }
        } catch (PDOException $ignored) {
            // Keep null result
        }

        // Final fallback for schemas that store email in AR_CUSTOMER.EMAIL
        if (!$customerCode) {
            try {
                $query3 = 'SELECT CODE FROM AR_CUSTOMER WHERE UPPER(TRIM(EMAIL)) = UPPER(TRIM(?))';
                $stmt3 = $con->prepare($query3);
                $stmt3->execute([$email]);
                $result3 = $stmt3->fetch(PDO::FETCH_ASSOC);
                if ($result3) {
                    $customerCode = $result3['CODE'];
                }
            } catch (PDOException $ignored) {
                // EMAIL column may not exist; ignore and keep null result.
            }
        }
    }
    
    if (!$customerCode) {
        echo json_encode([
            'success' => false,
            'error' => 'Customer not found',
            'data' => null
        ]);
        exit;
    }
    
    // Now fetch full customer details using the CODE
    $fullQuery = '
        SELECT 
            c.CODE,
            c.COMPANYNAME,
            c.CREDITTERM,
            cb.ADDRESS1,
            cb.ADDRESS2,
            cb.ADDRESS3,
            cb.ADDRESS4,
            cb.PHONE1
        FROM AR_CUSTOMER c
        LEFT JOIN AR_CUSTOMERBRANCH cb 
            ON cb.CODE = c.CODE
           AND cb.DTLKEY = (
               SELECT MIN(b.DTLKEY)
               FROM AR_CUSTOMERBRANCH b
               WHERE b.CODE = c.CODE
           )
        WHERE c.CODE = ?
    ';
    
    $fullStmt = $con->prepare($fullQuery);
    $fullStmt->execute([$customerCode]);
    $fullResult = $fullStmt->fetch(PDO::FETCH_ASSOC);
    
    if ($fullResult) {
        echo json_encode([
            'success' => true,
            'data' => [
                'CODE' => $fullResult['CODE'],
                'COMPANYNAME' => $fullResult['COMPANYNAME'] ?? 'N/A',
                'CREDITTERM' => $fullResult['CREDITTERM'] ?? 'N/A',
                'ADDRESS1' => $fullResult['ADDRESS1'] ?? 'N/A',
                'ADDRESS2' => $fullResult['ADDRESS2'] ?? 'N/A',
                'ADDRESS3' => $fullResult['ADDRESS3'] ?? '',
                'ADDRESS4' => $fullResult['ADDRESS4'] ?? '',
                'PHONE1' => $fullResult['PHONE1'] ?? 'N/A'
            ]
        ]);
    } else {
        echo json_encode([
            'success' => false,
            'error' => 'Customer data not found',
            'data' => null
        ]);
    }
    
} catch (PDOException $e) {
    echo json_encode(['success' => false, 'error' => 'Database error: ' . $e->getMessage()]);
} catch (Exception $e) {
    echo json_encode(['success' => false, 'error' => 'Error: ' . $e->getMessage()]);
} finally {
    if (isset($con)) {
        $con = null;
    }
}
?>
