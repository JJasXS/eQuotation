<?php
// getCustomerFullInfo.php - Get complete customer info including company name, address, and phone
// Joins AR_CUSTOMER and AR_CUSTOMERBRANCH using CODE
require_once 'db_helper.php';

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');

$customerCode = $_GET['customerCode'] ?? null;

if (!$customerCode) {
    echo json_encode(['success' => false, 'error' => 'customerCode parameter required']);
    exit;
}

try {
    $con = getFirebirdConnection();
    
    // Query joining AR_CUSTOMER and AR_CUSTOMERBRANCH
    // COMPANYNAME from AR_CUSTOMER, ADDRESS and PHONE from AR_CUSTOMERBRANCH
    $query = '
        SELECT 
            c.CODE,
            c.COMPANYNAME,
            c.CREDITTERM,
            cb.ADDRESS1,
            cb.ADDRESS2,
            cb.PHONE1
        FROM AR_CUSTOMER c
        LEFT JOIN AR_CUSTOMERBRANCH cb ON c.CODE = cb.CODE
        WHERE c.CODE = ?
    ';
    
    $stmt = $con->prepare($query);
    $stmt->execute([$customerCode]);
    $result = $stmt->fetch(PDO::FETCH_ASSOC);
    
    if ($result) {
        echo json_encode([
            'success' => true,
            'data' => [
                'CODE' => $result['CODE'],
                'COMPANYNAME' => $result['COMPANYNAME'] ?? 'N/A',
                'CREDITTERM' => $result['CREDITTERM'] ?? 'N/A',
                'ADDRESS1' => $result['ADDRESS1'] ?? 'N/A',
                'ADDRESS2' => $result['ADDRESS2'] ?? 'N/A',
                'PHONE1' => $result['PHONE1'] ?? 'N/A'
            ]
        ]);
    } else {
        echo json_encode([
            'success' => false,
            'error' => 'Customer not found'
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
