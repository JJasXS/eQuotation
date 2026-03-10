<?php
// getAllQuotations.php - Get all quotations for admin view with optional status filter
require_once 'db_helper.php';

header('Content-Type: application/json');

    $cancelled = isset($_GET['cancelled']) ? $_GET['cancelled'] : null; // Optional filter: 'true' or 'false'

try {
    $dbh = getFirebirdConnection();
    
    // Build query based on status filter
    $baseQuery = '
        SELECT qt.DOCKEY, qt.DOCNO, qt.DOCDATE, qt.CODE, qt.DESCRIPTION, 
               qt.DOCAMT, qt.CURRENCYCODE, qt.VALIDITY, qt.CANCELLED,
               ac.COMPANYNAME, ab.ADDRESS1, ab.PHONE1
        FROM SL_QT qt
        LEFT JOIN AR_CUSTOMER ac ON qt.CODE = ac.CODE
        LEFT JOIN AR_CUSTOMERBRANCH ab ON qt.CODE = ab.CODE
    ';
    if ($cancelled === 'true') {
        // Match both 'True' string and numeric 1 (Firebird stores as both formats)
        $query = $baseQuery . " WHERE (qt.CANCELLED = 'True' OR qt.CANCELLED = 1 OR qt.CANCELLED = -1) ORDER BY qt.DOCDATE DESC, qt.DOCKEY DESC";
        $stmt = $dbh->prepare($query);
        $stmt->execute();
    } elseif ($cancelled === 'false') {
        // Match both 'False' string and numeric 0
        $query = $baseQuery . " WHERE (qt.CANCELLED = 'False' OR qt.CANCELLED = 0) ORDER BY qt.DOCDATE DESC, qt.DOCKEY DESC";
        $stmt = $dbh->prepare($query);
        $stmt->execute();
    } else {
        $query = $baseQuery . ' ORDER BY qt.DOCDATE DESC, qt.DOCKEY DESC';
        $stmt = $dbh->prepare($query);
        $stmt->execute();
    }
    
    $quotations = $stmt->fetchAll(PDO::FETCH_ASSOC);
    
    // Format the data for consistency
    foreach ($quotations as &$qt) {
        $qt['DOCKEY'] = intval($qt['DOCKEY']);
        $qt['DOCAMT'] = floatval($qt['DOCAMT'] ?? 0);
        
        // Log original value before conversion
        $originalCancelled = $qt['CANCELLED'];
        
        // Handle CANCELLED: could be null, 'True'/'False' string, or 1/0 numeric, or boolean
        if ($qt['CANCELLED'] === null) {
            $qt['CANCELLED'] = null;
        } elseif (is_bool($qt['CANCELLED'])) {
            // Firebird sometimes returns as direct boolean
            $qt['CANCELLED'] = (bool)$qt['CANCELLED'];
        } elseif (is_numeric($qt['CANCELLED'])) {
            // Firebird stores as 1 (true), 0 (false), -1 (maybe true)
            $qt['CANCELLED'] = (intval($qt['CANCELLED']) !== 0);
        } else {
            // String values like 'True' or 'False'
            $qt['CANCELLED'] = (strtolower(trim((string)$qt['CANCELLED'])) === 'true');
        }
        
        // Log conversion for DOCKEY 31
        if ($qt['DOCKEY'] == 31) {
            error_log("[DEBUG] getAllQuotations DOCKEY 31: original=$originalCancelled, type=" . gettype($originalCancelled) . ", converted=" . ($qt['CANCELLED'] ? 'true' : 'false'));
        }
        
        $qt['COMPANYNAME'] = $qt['COMPANYNAME'] ?? 'N/A';
        $qt['ADDRESS1'] = $qt['ADDRESS1'] ?? 'N/A';
        $qt['PHONE1'] = $qt['PHONE1'] ?? 'N/A';
    }
    
    echo json_encode([
        'success' => true,
        'count' => count($quotations),
        'data' => $quotations
    ]);
    
} catch (Exception $e) {
    error_log("getAllQuotations.php error: " . $e->getMessage());
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}
?>
