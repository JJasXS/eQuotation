<?php
require_once 'db_helper.php';

header('Content-Type: application/json');

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    echo json_encode([
        'success' => false,
        'status' => 'error',
        'message' => 'POST method required'
    ]);
    exit;
}

$rawBody = file_get_contents('php://input');
$decoded = json_decode($rawBody, true);
$rules = [];

if (is_array($decoded) && isset($decoded['rules']) && is_array($decoded['rules'])) {
    $rules = $decoded['rules'];
} elseif (is_array($decoded)) {
    $rules = $decoded;
} elseif (isset($_POST['rules'])) {
    $postedRules = json_decode($_POST['rules'], true);
    if (is_array($postedRules)) {
        $rules = $postedRules;
    }
}

if (!is_array($rules) || count($rules) === 0) {
    echo json_encode([
        'success' => false,
        'status' => 'error',
        'message' => 'A non-empty rules array is required'
    ]);
    exit;
}

try {
    $dbh = getFirebirdConnection();
    $dbh->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);

    $ruleIds = [];
    foreach ($rules as $index => $rule) {
        $ruleId = isset($rule['PricingPriorityRuleId']) ? (int)$rule['PricingPriorityRuleId'] : 0;
        if ($ruleId <= 0) {
            throw new Exception('Each rule must include a valid PricingPriorityRuleId');
        }

        if (in_array($ruleId, $ruleIds, true)) {
            throw new Exception('Duplicate PricingPriorityRuleId found in payload');
        }
        $ruleIds[] = $ruleId;
    }

    $placeholders = implode(',', array_fill(0, count($ruleIds), '?'));
    $countStmt = $dbh->prepare("SELECT COUNT(*) AS CNT FROM PricingPriorityRule WHERE PricingPriorityRuleId IN ($placeholders)");
    $countStmt->execute($ruleIds);
    $matchedCount = (int)$countStmt->fetchColumn();
    if ($matchedCount !== count($ruleIds)) {
        throw new Exception('One or more pricing priority rules do not exist in database');
    }

    $dbh->beginTransaction();
    $updateStmt = $dbh->prepare(
        'UPDATE PricingPriorityRule
         SET PriorityNo = ?,
             IsEnabled = ?,
             EditDate = CURRENT_TIMESTAMP
         WHERE PricingPriorityRuleId = ?'
    );

    foreach ($rules as $index => $rule) {
        $priorityNo = $index + 1;
        $isEnabled = !empty($rule['IsEnabled']) ? 1 : 0;
        $ruleId = (int)$rule['PricingPriorityRuleId'];
        $updateStmt->execute([$priorityNo, $isEnabled, $ruleId]);
    }

    $dbh->commit();

    echo json_encode([
        'success' => true,
        'status' => 'success',
        'message' => 'Pricing priority rules saved successfully',
        'savedCount' => count($rules)
    ]);
} catch (Exception $e) {
    if (isset($dbh) && $dbh instanceof PDO && $dbh->inTransaction()) {
        $dbh->rollBack();
    }

    error_log('PricingPriorityRuleSave.php error: ' . $e->getMessage());
    echo json_encode([
        'success' => false,
        'status' => 'error',
        'message' => 'Failed to save pricing priority rules',
        'error' => $e->getMessage(),
    ]);
}
?>