<?php
// updateQuotationCancelled.php - Toggle CANCELLED status for a quotation
header('Content-Type: application/json');
require_once 'db_helper.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    echo json_encode(['success' => false, 'error' => 'POST method required']);
    exit;
}

$data = json_decode(file_get_contents('php://input'), true);
$dockey = $data['dockey'] ?? null;
$cancelledRaw = $data['cancelled'] ?? null;

// Normalize to boolean (JSON booleans, 0/1, or string "true"/"false" from some clients)
if (is_bool($cancelledRaw)) {
    $cancelled = $cancelledRaw;
} elseif (is_int($cancelledRaw) || is_float($cancelledRaw)) {
    $cancelled = ((int)$cancelledRaw) !== 0;
} elseif (is_string($cancelledRaw)) {
    $cancelled = in_array(strtolower(trim($cancelledRaw)), ['1', 'true', 'yes', 'on'], true);
} else {
    $cancelled = filter_var($cancelledRaw, FILTER_VALIDATE_BOOLEAN);
}

function normalizeCancelledValue($value) {
    if ($value === null) {
        return null;
    }
    if (is_bool($value)) {
        return $value;
    }
    if (is_int($value) || is_float($value)) {
        return ((int)$value) !== 0;
    }
    return in_array(strtolower(trim((string)$value)), ['1', 'true', 't', 'yes', 'y', 'on'], true);
}

error_log("[UPDATE QUOTATION] Received request: dockey=$dockey, cancelled=" . ($cancelled ? 'true' : 'false'));

if (!$dockey || $cancelledRaw === null) {
    error_log("[UPDATE QUOTATION] Missing parameters! dockey=$dockey, cancelled=" . var_export($cancelledRaw, true));
    echo json_encode(['success' => false, 'error' => 'dockey and cancelled required']);
    exit;
}

$dbh = null;
try {
    $dbh = getFirebirdConnection();
    $dbh->beginTransaction();
    error_log("[UPDATE QUOTATION] Database connection established");
    
    // Firebird BOOLEAN stored as 'True'/'False' strings
    $cancelledValue = $cancelled ? 'True' : 'False';
    error_log("[UPDATE QUOTATION] Setting DOCKEY=$dockey to CANCELLED='$cancelledValue'");
    
    // First, verify the record exists
    $checkStmt = $dbh->prepare('SELECT DOCKEY, DOCNO, CANCELLED FROM SL_QT WHERE DOCKEY = ?');
    $checkStmt->execute([$dockey]);
    $record = $checkStmt->fetch(PDO::FETCH_ASSOC);
    
    if (!$record) {
        throw new Exception("Quotation DOCKEY $dockey not found");
    }
    
    error_log("[UPDATE QUOTATION] Found record: DOCNO=" . $record['DOCNO'] . ", current CANCELLED=" . $record['CANCELLED']);
    
    // Always bump UPDATECOUNT on any CANCELLED toggle (activate or cancel). Firebird-safe integer math.
    $stmt = $dbh->prepare('
        UPDATE SL_QT SET
            CANCELLED = ?,
            UPDATECOUNT = COALESCE(CAST(UPDATECOUNT AS INTEGER), 0) + 1
        WHERE DOCKEY = ?
    ');
    $result = $stmt->execute([$cancelledValue, (int)$dockey]);
    
    error_log("[UPDATE QUOTATION] Update executed. Result=" . ($result ? 'true' : 'false'));
    error_log("[UPDATE QUOTATION] Rows affected: " . $stmt->rowCount());
    
    // Commit the transaction
    $dbh->commit();
    error_log("[UPDATE QUOTATION] Transaction committed");
    
    // Verify the update worked by querying again
    $verifyStmt = $dbh->prepare('SELECT CANCELLED FROM SL_QT WHERE DOCKEY = ?');
    $verifyStmt->execute([$dockey]);
    $verifiedRecord = $verifyStmt->fetch(PDO::FETCH_ASSOC);
    
    if ($verifiedRecord) {
        $verifiedValue = $verifiedRecord['CANCELLED'];
        error_log("[UPDATE QUOTATION] VERIFICATION: DOCKEY=$dockey now has CANCELLED='$verifiedValue'");

        $verifiedCancelled = normalizeCancelledValue($verifiedValue);
        if ($verifiedCancelled === $cancelled) {
            error_log("[UPDATE QUOTATION] ✓ SUCCESS: Update verified in database!");
            echo json_encode(['success' => true, 'message' => "Quotation $dockey updated to CANCELLED=$cancelledValue"]);
        } else {
            error_log("[UPDATE QUOTATION] ✗ VERIFICATION FAILED: Expected '" . ($cancelled ? 'true' : 'false') . "' but got '" . var_export($verifiedValue, true) . "'");
            echo json_encode(['success' => false, 'error' => "Update verification failed"]);
        }
    } else {
        error_log("[UPDATE QUOTATION] ✗ VERIFICATION FAILED: Record not found after update!");
        echo json_encode(['success' => false, 'error' => "Verification query returned no results"]);
    }
    
} catch (Exception $e) {
    error_log("[UPDATE QUOTATION] EXCEPTION: " . $e->getMessage());
    error_log("[UPDATE QUOTATION] Trace: " . $e->getTraceAsString());
    
    // Try to rollback if connection exists
    if ($dbh) {
        try {
            $dbh->rollBack();
            error_log("[UPDATE QUOTATION] Transaction rolled back");
        } catch (Exception $rollbackError) {
            error_log("[UPDATE QUOTATION] Rollback failed: " . $rollbackError->getMessage());
        }
    }
    
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
} finally {
    // Close connection
    $dbh = null;
}
