# SY_USER UDF flags (company schema)

Source: live `SY_USER` UDF columns. Truthy values: `1`, `Y`, `YES`, `T`, `TRUE`, `ON`, `-1` (and Firebird `BOOLEAN` true).

## Purchase side (e-PR / procurement)

| Column | Meaning |
|--------|---------|
| `UDF_ISPURMGR` | Purchase manager |
| `UDF_ISPURHOD` | Purchase HOD (**this** is purchase-side HOD — not a generic `UDF_ISHOD`) |
| `UDF_ISPURUSER` | Purchase user |

## Sales side

| Column | Meaning |
|--------|---------|
| `UDF_ISSALESMGR` | Sales manager |
| `UDF_ISSALESHOD` | Sales HOD |
| `UDF_ISSALESUSER` | Sales user |

## Production side

| Column | Meaning |
|--------|---------|
| `UDF_ISPRDMGR` | Production manager |
| `UDF_ISPRDHOD` | Production HOD |
| `UDF_ISPRDUSER` | Production user |

## Store side

| Column | Meaning |
|--------|---------|
| `UDF_ISSTRMGR` | Store manager |
| `UDF_ISSTRHOD` | Store HOD |
| `UDF_ISSTRUSER` | Store user |

## QA side

| Column | Meaning |
|--------|---------|
| `UDF_ISQAMGR` | QA manager |
| `UDF_ISQAHOD` | QA HOD |
| `UDF_ISQAUSER` | QA user |

## Finance side

| Column | Meaning |
|--------|---------|
| `UDF_ISFINMGR` | Finance manager |
| `UDF_ISFINHOD` | Finance HOD |
| `UDF_ISFINUSER` | Finance user |

## Cross-cutting

| Column | Meaning |
|--------|---------|
| `UDF_ISADMIN` | System admin |
| `UDF_ISDIRECTOR` | Director |

## Document approval flags

| Column | Document |
|--------|----------|
| `UDF_APPROVEIT` | IT |
| `UDF_APPROVEQT` | Quotation |
| `UDF_APPROVESO` | Sales order |
| `UDF_APPROVEDO` | Delivery order |
| `UDF_APPROVEIV` | Invoice |
| `UDF_APPROVECN` | Credit note |
| `UDF_APPROVEPQ` | Purchase quotation |
| `UDF_APPROVEPO` | Purchase order |
| `UDF_APPROVEGR` | Goods received |
| `UDF_APPROVEPI` | Purchase invoice |
| `UDF_APPROVEPR` | Purchase request / e-PR |
| `UDF_APPROVEST` | Stock transfer |
| `UDF_APPROVESA` | Stock adjustment |
| `UDF_APPROVESI` | Stock issue |
| `UDF_APPROVESR` | Stock receive |
| `UDF_APPROVEJO` | Job order |
| `UDF_APPROVEPV` | Payment voucher |
| `UDF_APPROVEJE` | Journal entry |

## Flat checklist (all columns)

```
UDF_ISADMIN
UDF_ISDIRECTOR
UDF_ISSALESMGR
UDF_ISSALESHOD
UDF_ISSALESUSER
UDF_ISPURMGR
UDF_ISPURHOD
UDF_ISPURUSER
UDF_ISPRDMGR
UDF_ISPRDHOD
UDF_ISPRDUSER
UDF_ISSTRMGR
UDF_ISSTRHOD
UDF_ISSTRUSER
UDF_ISQAMGR
UDF_ISQAHOD
UDF_ISQAUSER
UDF_ISFINMGR
UDF_ISFINHOD
UDF_ISFINUSER
UDF_APPROVEIT
UDF_APPROVEQT
UDF_APPROVESO
UDF_APPROVEDO
UDF_APPROVEIV
UDF_APPROVECN
UDF_APPROVEPQ
UDF_APPROVEPO
UDF_APPROVEGR
UDF_APPROVEPI
UDF_APPROVEPR
UDF_APPROVEST
UDF_APPROVESA
UDF_APPROVESI
UDF_APPROVESR
UDF_APPROVEJO
UDF_APPROVEPV
UDF_APPROVEJE
```

## Note for eQuotation Purchase / View e-PR

Purchase / View e-PR maps purchase HOD from **`UDF_ISPURHOD`** → session flag `ispurhod` → access tier `hod`.  
Sales/store/production/QA/finance HODs (`ISSALESHOD`, etc.) are **not** purchase access.
