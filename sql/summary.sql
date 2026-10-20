-- Сводные запросы поверх результата сверки.
-- Предполагается, что результат sql/reconciliation.sql сохранён в таблицу recon_result.

-- 1. Match rate по PSP за месяц
SELECT
    psp,
    COUNT(*)                                                    AS transactions,
    SUM(recon_result <> 'matched')                              AS breaks,
    ROUND(100.0 * SUM(recon_result = 'matched') / COUNT(*), 2)  AS match_rate_pct
FROM recon_result
GROUP BY psp
ORDER BY match_rate_pct;

-- 2. Расхождения по типам и PSP
SELECT psp, recon_result, COUNT(*) AS breaks, ROUND(SUM(break_amount_eur), 2) AS amount_eur
FROM recon_result
WHERE recon_result <> 'matched'
GROUP BY psp, recon_result
ORDER BY psp, breaks DESC;

-- 3. Дни, когда match rate по PSP падал ниже 99%
SELECT txn_date, psp,
       ROUND(100.0 * SUM(recon_result = 'matched') / COUNT(*), 2) AS match_rate_pct
FROM recon_result
GROUP BY txn_date, psp
HAVING match_rate_pct < 99
ORDER BY txn_date, psp;

-- 4. Контроль балансов: дельта факт − ожидание и флаг выше порога 500 €
SELECT balance_date, psp,
       ROUND(actual_balance_eur - expected_balance_eur, 2)              AS delta_eur,
       CASE WHEN ABS(actual_balance_eur - expected_balance_eur) > 500
            THEN 'above_threshold' ELSE 'ok' END                        AS flag
FROM balances
ORDER BY psp, balance_date;

-- 5. Эффективная комиссия и доля успешных транзакций по PSP
SELECT psp,
       ROUND(100.0 * SUM(successful) / SUM(transactions), 1) AS success_rate_pct,
       ROUND(SUM(volume_eur), 0)                             AS volume_eur,
       ROUND(SUM(fee_eur), 0)                                AS fee_eur,
       ROUND(100.0 * SUM(fee_eur) / SUM(volume_eur), 2)      AS effective_fee_pct
FROM payments_weekly
GROUP BY psp
ORDER BY effective_fee_pct;
