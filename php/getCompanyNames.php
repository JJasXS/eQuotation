<?php
// getCompanyNames.php - Get all unique company names from AR_CUSTOMER
require_once 'db_helper.php';

header('Content-Type: application/json');

$dbh = null;

try {
    $dbh = getFirebirdConnection();
    
    $query = '
        SELECT DISTINCT ac.COMPANYNAME
        FROM AR_CUSTOMER ac
        ORDER BY ac.COMPANYNAME ASC
    ';
    
    $stmt = $dbh->prepare($query);
    $stmt->execute();
    
    $companies = $stmt->fetchAll(PDO::FETCH_ASSOC);
    
    // Extract just the company names
    $companyNames = array_map(function($row) {
        return trim($row['COMPANYNAME']);
    }, $companies);
    
    // Remove empty values and duplicates
    $companyNames = array_unique(array_filter($companyNames));
    $companyNames = array_values($companyNames); // Re-index array
    
    echo json_encode([
        'success' => true,
        'count' => count($companyNames),
        'data' => $companyNames
    ]);
    
} catch (Exception $e) {
    error_log("getCompanyNames.php error: " . $e->getMessage());
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
} finally {
    $dbh = null;
}
?>
