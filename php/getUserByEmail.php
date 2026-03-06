<?php
// getUserByEmail.php - Get user information by email from AR_CUSTOMERBRANCH table
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
    
    // Query AR_CUSTOMERBRANCH table by EMAIL
    $query = 'SELECT CODE, EMAIL FROM AR_CUSTOMERBRANCH WHERE EMAIL = ?';
    $stmt = $con->prepare($query);
    $stmt->execute([$email]);
    $result = $stmt->fetch(PDO::FETCH_ASSOC);
    
    if ($result) {
        echo json_encode([
            'success' => true,
            'data' => $result
        ]);
    } else {
        echo json_encode([
            'success' => false,
            'error' => 'User not found',
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
