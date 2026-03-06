<?php
// db_helper.php - Firebird DB connection helper
function getFirebirdConnection() {
    $host = 'localhost';
    $db = 'C:/eStream/SQLAccounting/DB/ACC-0001.FDB';
    $user = 'sysdba';
    $pass = 'masterkey';
    try {
        $dbh = new PDO("firebird:dbname=$db;host=$host", $user, $pass);
        return $dbh;
    } catch (PDOException $e) {
        // You can handle the error here or rethrow
        throw $e;
    }
}
?>
