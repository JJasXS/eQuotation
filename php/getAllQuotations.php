<?php
// getAllQuotations.php - Get all quotations for admin view with optional status filter
require_once 'db_helper.php';

header('Content-Type: application/json');
ob_start(); // Prevent accidental output

$cancelled = isset($_GET['cancelled']) ? $_GET['cancelled'] : null; // Optional filter: 'true' or 'false'

error_log("[getAllQuotations] Starting. cancelled param = " . var_export($cancelled, true));

try {
    $dbh = getFirebirdConnection();
    error_log("[getAllQuotations] Database connection successful");
    
    // Build query based on status filter
    $baseQuery = '
        SELECT qt.DOCKEY, qt.DOCNO, qt.DOCDATE, qt.CODE, qt.DESCRIPTION, 
               qt.DOCAMT, qt.CURRENCYCODE, qt.VALIDITY, qt.CANCELLED, qt.UPDATECOUNT,
               ac.COMPANYNAME, ab.ADDRESS1, ab.PHONE1
        FROM SL_QT qt
        LEFT JOIN AR_CUSTOMER ac ON qt.CODE = ac.CODE
        LEFT JOIN AR_CUSTOMERBRANCH ab ON qt.CODE = ab.CODE
    ';
    
    if ($cancelled === 'true') {
        // Match both 'True' string and numeric 1 (Firebird stores as both formats)
        $query = $baseQuery . " WHERE (qt.CANCELLED = 'True' OR qt.CANCELLED = 1 OR qt.CANCELLED = -1) ORDER BY qt.DOCDATE DESC, qt.DOCKEY DESC";
        error_log("[getAllQuotations] Executing query with cancelled=true filter");
    } elseif ($cancelled === 'false') {
        // Match both 'False' string and numeric 0
        $query = $baseQuery . " WHERE (qt.CANCELLED = 'False' OR qt.CANCELLED = 0) ORDER BY qt.DOCDATE DESC, qt.DOCKEY DESC";
        error_log("[getAllQuotations] Executing query with cancelled=false filter");
    } else {
        $query = $baseQuery . ' ORDER BY qt.DOCDATE DESC, qt.DOCKEY DESC';
        error_log("[getAllQuotations] Executing query with no filter (all quotations)");
    }
    
    $stmt = $dbh->prepare($query);
    $stmt->execute();
    
    error_log("[getAllQuotations] Query executed successfully");
    
    $quotations = $stmt->fetchAll(PDO::FETCH_ASSOC);
    error_log("[getAllQuotations] Fetched " . count($quotations) . " quotations");
    
    // Format the data for consistency
    foreach ($quotations as &$qt) {
        $qt['DOCKEY'] = intval($qt['DOCKEY']);
        $qt['DOCAMT'] = floatval($qt['DOCAMT'] ?? 0);
        $qt['UPDATECOUNT'] = ($qt['UPDATECOUNT'] === null) ? null : intval($qt['UPDATECOUNT']);
        
        // Log original value before conversion
        $originalCancelled = $qt['CANCELLED'];
        
        // Preserve NULL so the UI can distinguish Pending from Active.
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
        
        $qt['COMPANYNAME'] = $qt['COMPANYNAME'] ?? 'N/A';
        $qt['ADDRESS1'] = $qt['ADDRESS1'] ?? 'N/A';
        $qt['PHONE1'] = $qt['PHONE1'] ?? 'N/A';
    }
    
    ob_end_clean();
    echo json_encode([
        'success' => true,
        'count' => count($quotations),
        'data' => $quotations
    ]);
    error_log("[getAllQuotations] Response sent successfully with " . count($quotations) . " quotations");
    
} catch (Exception $e) {
    ob_end_clean();
    error_log("[getAllQuotations] EXCEPTION: " . $e->getMessage());
    error_log("[getAllQuotations] Trace: " . $e->getTraceAsString());
    
    echo json_encode([
        'success' => false, 
        'error' => $e->getMessage(),
        'trace' => $e->getTraceAsString()
    ]);
}
?>
