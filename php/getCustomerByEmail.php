<?php
// getCustomerByEmail.php - Get customer code from AR_CUSTOMERBRANCH by email
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

try {
    $con = getFirebirdConnection();
    
    // Query AR_CUSTOMERBRANCH for customer code
    $query = 'SELECT CODE FROM AR_CUSTOMERBRANCH WHERE EMAIL = ?';
    $stmt = $con->prepare($query);
    $stmt->execute([$email]);
    $result = $stmt->fetch(PDO::FETCH_ASSOC);
    
    if ($result) {
        echo json_encode([
            'success' => true,
            'customerCode' => $result['CODE']
        ]);
    } else {
        // If not found in AR_CUSTOMERBRANCH, check AR_CUSTOMER.UDF_EMAIL
        $result2 = null;
        try {
            $query2 = 'SELECT CODE FROM AR_CUSTOMER WHERE UDF_EMAIL = ?';
            $stmt2 = $con->prepare($query2);
            $stmt2->execute([$email]);
            $result2 = $stmt2->fetch(PDO::FETCH_ASSOC);
        } catch (PDOException $ignored) {
            // Keep null result; return not found instead of hard error
        }

        if ($result2) {
            echo json_encode([
                'success' => true,
                'customerCode' => $result2['CODE']
            ]);
        } else {
            echo json_encode([
                'success' => false,
                'error' => 'Customer not found',
                'customerCode' => null
            ]);
        }
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
