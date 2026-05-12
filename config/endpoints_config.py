# endpoints_config.py
# Paths proxied or opened from main.py against BASE_API_URL (PHP bridge).

BASE_API_URL = "http://localhost:8080"

ENDPOINT_PATHS = {
    "getordersbystatus": "/php/getOrdersByStatus.php",
    "updateorderstatus": "/php/updateOrderStatus.php",
    "getorderdetails": "/php/getOrderDetails.php",
    "updateorderdetail": "/php/updateOrderDetail.php",
    "insertorderdetail": "/php/insertOrderDetail.php",
    "getcompanynames": "/php/getCompanyNames.php",
}
