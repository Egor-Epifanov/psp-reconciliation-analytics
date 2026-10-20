-- Ежедневная сверка: внутренний учёт (ledger) против отчёта PSP (psp_report)
-- Диалект: SQLite 3.39+ (нужен FULL OUTER JOIN). В PostgreSQL работает без изменений.
--
-- Для каждой транзакции определяет результат сверки:
--   matched            — всё совпало
--   missing_in_psp     — есть в учёте, нет в отчёте PSP
--   missing_in_ledger  — есть в отчёте PSP, нет в учёте
--   status             — разный статус (например, у нас success, у PSP failed)
--   amount             — разная сумма
--   fee                — разная комиссия
-- и сумму расхождения в евро.

WITH recon AS (
    SELECT
        COALESCE(l.txn_id,   p.txn_id)   AS txn_id,
        COALESCE(l.txn_date, p.txn_date) AS txn_date,
        COALESCE(l.psp,      p.psp)      AS psp,
        l.amount_eur AS ledger_amount, p.amount_eur AS psp_amount,
        l.fee_eur    AS ledger_fee,    p.fee_eur    AS psp_fee,
        l.status     AS ledger_status, p.status     AS psp_status,
        CASE
            WHEN p.txn_id IS NULL                         THEN 'missing_in_psp'
            WHEN l.txn_id IS NULL                         THEN 'missing_in_ledger'
            WHEN l.status <> p.status                     THEN 'status'
            WHEN ABS(l.amount_eur - p.amount_eur) > 0.01  THEN 'amount'
            WHEN ABS(l.fee_eur - p.fee_eur) > 0.01        THEN 'fee'
            ELSE 'matched'
        END AS recon_result
    FROM ledger l
    FULL OUTER JOIN psp_report p ON l.txn_id = p.txn_id
)
SELECT
    txn_id, txn_date, psp, recon_result,
    ledger_status, psp_status,
    ledger_amount, psp_amount, ledger_fee, psp_fee,
    ROUND(CASE recon_result
        WHEN 'missing_in_psp'    THEN ledger_amount
        WHEN 'missing_in_ledger' THEN psp_amount
        WHEN 'status'            THEN ledger_amount
        WHEN 'amount'            THEN ABS(ledger_amount - psp_amount)
        WHEN 'fee'               THEN ABS(ledger_fee - psp_fee)
        ELSE 0
    END, 2) AS break_amount_eur
FROM recon;
