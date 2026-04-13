-- App-owned sequence setup for concurrency-safe key allocation.
-- MAX(id)+1 is unsafe when concurrent sessions insert at the same time.

CREATE SEQUENCE SEQ_CHAT_TPLDTL_MESSAGEID;
CREATE SEQUENCE SEQ_ORDER_TPL_ORDERID;
CREATE SEQUENCE SEQ_ORDER_TPLDTL_ORDERDTLID;
