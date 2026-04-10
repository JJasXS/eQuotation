<?php
require_once 'db_helper.php';

header('Content-Type: application/json');

if ($_SERVER['REQUEST_METHOD'] !== 'GET') {
    echo json_encode([
        'success' => false,
        'status' => 'error',
        'message' => 'GET method required'
    ]);
    exit;
}

$dbh = null;

try {
    $dbh = getFirebirdConnection();
    $stmt = $dbh->prepare(
        'SELECT PricingPriorityRuleId, RuleCode, RuleName, PriorityNo, IsEnabled
         FROM PricingPriorityRule
         ORDER BY PriorityNo ASC, PricingPriorityRuleId ASC'
    );
    $stmt->execute();

    $rules = [];
    while ($row = $stmt->fetch(PDO::FETCH_ASSOC)) {
        $rules[] = [
            'PricingPriorityRuleId' => (int)($row['PRICINGPRIORITYRULEID'] ?? 0),
            'RuleCode' => trim((string)($row['RULECODE'] ?? '')),
            'RuleName' => trim((string)($row['RULENAME'] ?? '')),
            'PriorityNo' => (int)($row['PRIORITYNO'] ?? 0),
            'IsEnabled' => (int)($row['ISENABLED'] ?? 0),
        ];
    }

    echo json_encode([
        'success' => true,
        'status' => 'success',
        'message' => 'Pricing priority rules loaded successfully',
        'data' => $rules,
    ]);
} catch (Exception $e) {
    error_log('PricingPriorityRuleGet.php error: ' . $e->getMessage());
    echo json_encode([
        'success' => false,
        'status' => 'error',
        'message' => 'Failed to load pricing priority rules',
        'error' => $e->getMessage(),
    ]);
} finally {
    $dbh = null;
}
?>