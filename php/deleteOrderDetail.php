<?php
// deleteOrderDetail.php - Remove line item from order
require_once 'db_helper.php';

header('Content-Type: application/json');

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    badRequest('POST method required');
    exit;
}

$data = json_decode(file_get_contents('php://input'), true);
$orderdtlid = $data['orderdtlid'] ?? null;

if (!$orderdtlid) {
    badRequest('orderdtlid required');
    exit;
}

$dbh = null;

try {
    $dbh = getFirebirdConnection();
    $dbh->beginTransaction();
    
    // Get description before deleting (for response message)
    $stmt = $dbh->prepare('SELECT DESCRIPTION FROM ORDER_TPLDTL WHERE ORDERDTLID = ?');
    $stmt->execute([$orderdtlid]);
    $result = $stmt->fetch(PDO::FETCH_ASSOC);
    if (!$result) {
        throw new RuntimeException('Order detail not found', 404);
    }
    $description = $result['DESCRIPTION'] ?? 'Item';
    
    // Delete order detail
    $stmt = $dbh->prepare('DELETE FROM ORDER_TPLDTL WHERE ORDERDTLID = ?');
    $stmt->execute([$orderdtlid]);
    if ($stmt->rowCount() === 0) {
        throw new RuntimeException('Order detail not found', 404);
    }

    $dbh->commit();
    
    jsonResponse(200, true, "Removed $description from order", ['orderdtlid' => (int)$orderdtlid], null);
} catch (RuntimeException $e) {
    if ($dbh instanceof PDO && $dbh->inTransaction()) {
        $dbh->rollBack();
    }
    if ($e->getCode() === 404) {
        notFound($e->getMessage());
    } else {
        badRequest($e->getMessage());
    }
} catch (Exception $e) {
    if ($dbh instanceof PDO && $dbh->inTransaction()) {
        $dbh->rollBack();
    }
    serverError('Failed to delete order detail');
} finally {
    $dbh = null;
}
?>
