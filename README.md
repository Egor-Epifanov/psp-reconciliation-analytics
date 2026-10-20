# Сверка платежей с PSP: SQL + pandas

Ежедневная работа платёжной команды iGaming-оператора: депозиты и выводы игроков через три платёжных провайдера (PSP) за сентябрь 2026. Все суммы в рублях, названия PSP условные. Логика сверки взята из моей работы со сверками эквайринговых и платёжных транзакций в банке.

**Интерактивные дашборды:** [egor-epifanov.github.io/psp-reconciliation-analytics](https://egor-epifanov.github.io/psp-reconciliation-analytics/) · [сверка](https://egor-epifanov.github.io/psp-reconciliation-analytics/recon.html) · [балансы](https://egor-epifanov.github.io/psp-reconciliation-analytics/balances.html) · [платёжный отчёт](https://egor-epifanov.github.io/psp-reconciliation-analytics/payments.html)

![Match rate по дням](charts/match_rate_daily.png)

## Что внутри

| Задача | Как решаю | Где смотреть |
|---|---|---|
| Сверка учёта с отчётами PSP | FULL OUTER JOIN по ID транзакции, классификация расхождений: статус, сумма, комиссия, нет у PSP, нет в учёте | [`sql/reconciliation.sql`](sql/reconciliation.sql) |
| Качество данных до отчётности | Проверка на дубли, пропуски, некорректные суммы | [ноутбук, раздел 1](notebooks/psp_reconciliation.ipynb) |
| Match rate по PSP и по дням | Доля сверенных транзакций, дни ниже порога 99% | [ноутбук, раздел 2](notebooks/psp_reconciliation.ipynb) |
| Контроль балансов на PSP | Ожидаемый баланс по учёту против факта из выписки, порог эскалации 50 000 ₽ | [`sql/summary.sql`](sql/summary.sql), раздел 3 ноутбука |
| Отчёт для трейдеров | Оборот, доля успешных платежей, эффективная комиссия по PSP и странам | раздел 4 ноутбука |

## Главные результаты

- **11 738 транзакций**, **53 расхождения**, общий match rate **99,55%**.
- **PSP Gamma** даёт 38 из 53 расхождений при самом маленьком объёме, match rate 98,25%. Пик 14–17 сентября.
- **Балансы:** у PSP Beta разовый провал 9–10 сентября до −98 636 ₽ (задержка зачисления), у PSP Gamma с 14 сентября нарастающая недоплата до −57 379 ₽. Совпадает по времени со всплеском расхождений по комиссиям.
- **Стоимость провайдеров:** эффективная комиссия PSP Alfa 1,87%, PSP Gamma 2,99%. Gamma дороже почти в 1,6 раза и теряет каждую пятую транзакцию.

| PSP | Успешные, % | Оборот, ₽ | Комиссии, ₽ | Эффективная комиссия |
|---|---|---|---|---|
| PSP Alfa | 91,9 | 63 081 038 | 1 178 920 | 1,87% |
| PSP Beta | 86,5 | 39 027 381 | 915 708 | 2,35% |
| PSP Gamma | 80,2 | 22 017 250 | 659 256 | 2,99% |

![Дельта баланса](charts/balance_delta.png)

## Структура

```
data/                 CSV: ledger, psp_report, balances, payments_weekly
sql/reconciliation.sql  сверка учёта с отчётами PSP
sql/summary.sql         сводные запросы: match rate, типы расхождений, балансы, комиссии
notebooks/              ноутбук с анализом и графиками
charts/                 графики из ноутбука
docs/                   интерактивные дашборды (GitHub Pages)
src/generate_data.py    сборка исходных CSV в data/
src/build_dashboards.py сборка дашбордов в docs/
```

## Как запустить

```bash
pip install -r requirements.txt
jupyter notebook notebooks/psp_reconciliation.ipynb
```

SQL написан для SQLite 3.39+ и без изменений работает в PostgreSQL.

## Стек

SQL · Python · pandas · matplotlib · Jupyter · Chart.js

---

**Егор Епифанов** · аналитик данных, сверки и финансовая отчётность · Белград
[Telegram](https://t.me/pretty_rom) · egorka.epifanov.2k17@gmail.com
