"""
Сборка исходных данных проекта. Все суммы в рублях.

Модель повторяет платёжные процессы российского онлайн-букмекера: депозиты и выводы
игроков через три PSP за сентябрь 2026. Названия PSP условные.

Что создаётся в папке data/:
  ledger.csv           — транзакции по внутреннему учёту
  psp_report.csv       — те же транзакции по отчётам PSP (с внесёнными расхождениями)
  balances.csv         — ожидаемый и фактический баланс на счёте у каждого PSP по дням
  payments_weekly.csv  — агрегаты платежей по неделям, PSP, регионам и типам операций

Запуск: python src/generate_data.py
"""
import csv
import datetime as dt
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data"
OUT.mkdir(exist_ok=True)

PSP = ["PSP Alfa", "PSP Beta", "PSP Gamma"]
CODE = {"PSP Alfa": "ALF", "PSP Beta": "BET", "PSP Gamma": "GAM"}
START = dt.date(2026, 9, 1)
DAYS = [START + dt.timedelta(d) for d in range(30)]
VOLUME = {"PSP Alfa": 180, "PSP Beta": 120, "PSP Gamma": 70}
BREAK_TYPES = ["status", "amount", "fee", "missing_in_psp", "missing_in_ledger"]
BREAK_WEIGHTS = {"PSP Alfa": [2, 1, 3, 1, 1], "PSP Beta": [2, 1, 1, 1, 1], "PSP Gamma": [1, 2, 5, 1, 2]}
BREAK_SIZE = {"status": (2000, 40000), "amount": (100, 3000), "fee": (50, 1200),
              "missing_in_psp": (2000, 30000), "missing_in_ledger": (1000, 20000)}

rnd = random.Random(42)      # сценарий: объёмы, расхождения, балансы, платежи
txn_rnd = random.Random(7)   # детали отдельных транзакций


def money(x):
    return round(x, 2)


def scenario():
    """Сколько транзакций в день по каждому PSP и какие расхождения в них заложены."""
    plan = []
    for d in DAYS:
        for p in PSP:
            n = int(VOLUME[p] * rnd.uniform(.85, 1.2) * (1.15 if d.weekday() >= 5 else 1))
            weights = [14, 5, 2, 0, 0, 0] if p != "PSP Gamma" else [6, 6, 3, 1, 0, 0]
            k = rnd.choices(range(6), weights=weights)[0]
            if p == "PSP Gamma" and 14 <= d.day <= 17:   # всплеск у PSP Gamma
                k += 2
            breaks = []
            for _ in range(k):
                t = rnd.choices(BREAK_TYPES, weights=BREAK_WEIGHTS[p])[0]
                sizes = {bt: rnd.uniform(*BREAK_SIZE[bt]) for bt in BREAK_TYPES}
                size = money(sizes[t])
                age = (DAYS[-1] - d).days
                if 1 < age <= 5:     # статус разбора в журнале: свежие расхождения ещё не закрыты
                    rnd.choice(["closed", "in_progress", "open"])
                elif age <= 1:
                    rnd.choice(["in_progress", "open"])
                breaks.append((t, size))
            plan.append((d, p, n, breaks))
    return plan


def transactions(plan):
    ledger, psp_report = [], []
    for d, p, n, breaks in plan:
        for i in range(n):
            txn_id = f"{CODE[p]}-{d:%m%d}-{i:04d}"
            typ = txn_rnd.choices(["deposit", "withdrawal"], weights=[83, 17])[0]
            amount = money(txn_rnd.uniform(1000, 40000) if typ == "deposit" else txn_rnd.uniform(4000, 60000))
            status = txn_rnd.choices(["success", "failed"], weights=[88, 12])[0]
            rate = {"PSP Alfa": .022, "PSP Beta": .028, "PSP Gamma": .035}[p]
            fee = money(amount * rate * (1 if typ == "deposit" else .55)) if status == "success" else 0.0
            row = dict(txn_id=txn_id, txn_date=d.isoformat(), psp=p, type=typ,
                       amount_rub=amount, fee_rub=fee, status=status)
            l_row, p_row = dict(row), dict(row)
            if i < len(breaks):
                b, size = breaks[i]
                if b == "status":
                    l_row.update(amount_rub=size, status="success")
                    p_row.update(amount_rub=size, status="failed", fee_rub=0.0)
                    l_row["fee_rub"] = money(size * rate)
                elif b == "amount":
                    p_row["amount_rub"] = money(amount - size)
                elif b == "fee":
                    l_row["status"] = p_row["status"] = "success"
                    l_row["fee_rub"] = p_row["fee_rub"] = money(amount * rate)
                    p_row["fee_rub"] = money(p_row["fee_rub"] + size)
                elif b == "missing_in_psp":
                    l_row["amount_rub"] = size
                    p_row = None
                elif b == "missing_in_ledger":
                    p_row["amount_rub"] = size
                    l_row = None
            if l_row:
                ledger.append(l_row)
            if p_row:
                psp_report.append(p_row)
    txn_rnd.shuffle(psp_report)
    return ledger, psp_report


def balances():
    rows = []
    for p in PSP:
        expected = rnd.uniform(4000000, 9000000)
        for d in DAYS:
            expected += rnd.uniform(-600000, 800000)
            delta = rnd.uniform(-15000, 15000)
            if p == "PSP Gamma" and d.day >= 14:          # нарастающая недоплата
                delta -= (d.day - 13) * 3500
            if p == "PSP Beta" and d.day in (9, 10):      # разовая задержка зачисления
                delta -= 90000
            rows.append(dict(balance_date=d.isoformat(), psp=p,
                             expected_balance_rub=money(expected),
                             actual_balance_rub=money(expected + delta)))
    return rows


def payments():
    regions = {"Москва": 1.0, "Другие регионы": .6, "Санкт-Петербург": .4}
    fee = {"PSP Alfa": (.022, .012), "PSP Beta": (.028, .015), "PSP Gamma": (.035, .02)}
    success = {"PSP Alfa": .93, "PSP Beta": .88, "PSP Gamma": .81}
    rows = []
    for w in ["2026-W36", "2026-W37", "2026-W38", "2026-W39"]:
        for p in PSP:
            for c, cm in regions.items():
                for typ in ["deposit", "withdrawal"]:
                    n = int(VOLUME[p] * 7 * cm * (1 if typ == "deposit" else .2) * rnd.uniform(.9, 1.1))
                    sr = success[p] + rnd.uniform(-.03, .03) - (.05 if c == "Другие регионы" else 0)
                    ok = int(n * sr)
                    avg = rnd.uniform(3500, 5500) if typ == "deposit" else rnd.uniform(9000, 14000)
                    volume = money(ok * avg)
                    rows.append(dict(week=w, psp=p, region=c, type=typ, transactions=n,
                                     successful=ok, failed=n - ok, volume_rub=volume,
                                     fee_rub=money(volume * fee[p][0 if typ == "deposit" else 1])))
    return rows


def write(name, rows):
    with open(OUT / name, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{name}: {len(rows)} строк")


if __name__ == "__main__":
    plan = scenario()
    ledger, psp_report = transactions(plan)
    write("ledger.csv", ledger)
    write("psp_report.csv", psp_report)
    write("balances.csv", balances())
    write("payments_weekly.csv", payments())
