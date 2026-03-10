# endpoints_config.py
# Central config for API base URL and endpoint paths

BASE_API_URL = "http://localhost"

ENDPOINT_PATHS = {
    "stockitem": "/php/getStockItem.php",
    "stockitemprice": "/php/getStockItemPrice.php",
    "stockitembydescription": "/php/getStockItemByDescription.php",
    "chatbyid": "/php/getChatByID.php",
    "chattpldtl": "/php/getChatTPLDTL.php",
        "getuserinfo": "/php/getUserInfo.php",  # This line is retained as it already exists
    "getadminbyemail": "/php/getAdminByEmail.php",
    "getuserbyemail": "/php/getUserByEmail.php",
    "getcustomerbyemail": "/php/getCustomerByEmail.php",
    "getcustomerbyemailfromcustomer": "/php/getCustomerByEmail.php",
    "getcustomerfullinfo": "/php/getCustomerFullInfo.php",
    "getdraftorders": "/php/getDraftOrders.php",
    "getorderdetails": "/php/getOrderDetails.php",
    "getorderremarks": "/php/getOrderRemarks.php",
    "getordersbystatus": "/php/getOrdersByStatus.php",
    "getquotationdetails": "/php/getQuotationDetails.php",
    "getallquotations": "/php/getAllQuotations.php",
    "getcompanynames": "/php/getCompanyNames.php",
    "getchats": "/php/getChats.php",
    "getchatdetails": "/php/getChatDetails.php",
    "getallorders": "/php/getAllOrders.php",
    "getstockitem": "/php/getStockItem.php",
    "getstockitemprice": "/php/getStockItemPrice.php",
    "insertchatmessage": "/php/insertChatMessage.php",
    "insertdraftquotation": "/php/insertDraftQuotation.php",
    "insertorder": "/php/insertOrder.php",
    "insertorderbymanual": "/php/insertOrderByManual.php",
    "insertorderdetail": "/php/insertOrderDetail.php",
    "insertquotationbymanual": "/php/insertQuotationByManual.php",
    "insertquotationtoaccounting": "/php/insertQuotationToAccounting.php",
    "requestorderchange": "/php/requestOrderChange.php",
    "updateorderstatus": "/php/updateOrderStatus.php",
    "updateorderdetail": "/php/updateOrderDetail.php",
    "updatedraftquotation": "/php/updateDraftQuotation.php",
    "deletedorderdetail": "/php/deleteOrderDetail.php",
    "checkdraftorder": "/php/checkDraftOrder.php",
    "completeorder": "/php/completeOrder.php",
    "createsigninuser": "/php/createSignInUser.php",
    # db_helper.php is likely an internal helper, not an endpoint
}
