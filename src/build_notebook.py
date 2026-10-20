"""Собирает notebooks/psp_reconciliation.ipynb из ячеек ниже."""
from pathlib import Path
import nbformat as nbf

md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell
cells = [
md("""# Сверка платежей с PSP: учёт против отчётов платёжных систем

Собственный проект, все суммы в рублях. Модель повторяет ежедневную работу платёжной команды iGaming-оператора: депозиты и выводы игроков через три PSP за сентябрь 2026.

Что делаю в ноутбуке:
1. Проверяю качество данных до сверки: дубли, пропуски.
2. Свожу внутренний учёт с отчётами PSP SQL-запросом и нахожу расхождения по статусам, суммам и комиссиям.
3. Считаю match rate по PSP и по дням, ищу аномальные дни.
4. Контролирую балансы на счетах PSP: ожидание против факта.
5. Собираю отчёт для трейдеров: оборот, отказы, эффективная комиссия."""),
code("""import sqlite3
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path('..')
DATA, CHARTS = ROOT / 'data', ROOT / 'charts'
CHARTS.mkdir(exist_ok=True)

COLORS = {'PSP Alfa': '#2F6FDE', 'PSP Beta': '#8B5CF6', 'PSP Gamma': '#F08A24'}
plt.rcParams.update({'axes.spines.top': False, 'axes.spines.right': False,
                     'axes.grid': True, 'grid.color': '#EEF0F3', 'axes.axisbelow': True,
                     'figure.dpi': 110})

ledger = pd.read_csv(DATA / 'ledger.csv')
psp_report = pd.read_csv(DATA / 'psp_report.csv')
balances = pd.read_csv(DATA / 'balances.csv')
payments = pd.read_csv(DATA / 'payments_weekly.csv')
print(f'Учёт: {len(ledger):,} строк · отчёты PSP: {len(psp_report):,} строк'.replace(',', ' '))"""),
md("## 1. Качество данных до сверки"),
code("""checks = pd.DataFrame({
    'дубли txn_id': [ledger.txn_id.duplicated().sum(), psp_report.txn_id.duplicated().sum()],
    'пустые значения': [ledger.isna().sum().sum(), psp_report.isna().sum().sum()],
    'отрицательные суммы': [(ledger.amount_rub < 0).sum(), (psp_report.amount_rub < 0).sum()],
}, index=['ledger', 'psp_report'])
checks"""),
md("## 2. Сверка SQL-запросом\nЗапрос лежит в `sql/reconciliation.sql`: FULL OUTER JOIN по `txn_id` и классификация каждой транзакции."),
code("""con = sqlite3.connect(':memory:')
for name, df in {'ledger': ledger, 'psp_report': psp_report,
                 'balances': balances, 'payments_weekly': payments}.items():
    df.to_sql(name, con, index=False)

recon = pd.read_sql((ROOT / 'sql' / 'reconciliation.sql').read_text(encoding='utf-8'), con)
recon.to_sql('recon_result', con, index=False)
breaks = recon[recon.recon_result != 'matched']

total, n_breaks = len(recon), len(breaks)
print(f'Транзакций: {total} · расхождений: {n_breaks} · match rate: {100 * (1 - n_breaks / total):.2f}%')"""),
code("""by_psp = (recon.assign(is_break=recon.recon_result != 'matched')
          .groupby('psp').agg(transactions=('txn_id', 'size'), breaks=('is_break', 'sum')))
by_psp['match_rate_pct'] = (100 * (1 - by_psp.breaks / by_psp.transactions)).round(2)
by_psp"""),
code("""pivot = breaks.pivot_table(index='psp', columns='recon_result', values='txn_id', aggfunc='count', fill_value=0)
ax = pivot.plot(kind='bar', stacked=True, figsize=(9, 4), rot=0,
                color=['#2F6FDE', '#8B5CF6', '#E5B800', '#F08A24', '#D14343'][:pivot.shape[1]])
ax.set_title('Расхождения по PSP и типу', loc='left', fontweight='bold')
ax.set_xlabel(''); ax.set_ylabel('расхождений, шт.'); ax.legend(frameon=False, ncol=5, fontsize=8)
plt.tight_layout(); plt.savefig(CHARTS / 'breaks_by_psp.png'); plt.show()"""),
md("### Match rate по дням\nИщу дни, когда доля сверенных транзакций у PSP падает ниже 99%."),
code("""daily = (recon.assign(ok=recon.recon_result == 'matched')
         .groupby(['txn_date', 'psp']).ok.mean().mul(100).unstack())
ax = daily.plot(figsize=(10, 4), color=[COLORS[c] for c in daily.columns], lw=2)
ax.axhline(99, color='#D14343', ls='--', lw=1)
ax.set_title('Match rate по дням, %', loc='left', fontweight='bold')
ax.set_xlabel(''); ax.legend(frameon=False, ncol=3)
plt.tight_layout(); plt.savefig(CHARTS / 'match_rate_daily.png'); plt.show()

low = daily.stack().round(2).rename('match_rate_pct').reset_index()
low[low.match_rate_pct < 99]"""),
md("""**Вывод.** PSP Gamma даёт большую часть расхождений, хотя проводит меньше всего транзакций, и регулярно опускается ниже 99%. Пик 14–17 сентября: стоит проверить у провайдера, не менялись ли тарифы или формат выгрузки.

Журнал открытых расхождений для разбора:"""),
code("""breaks.sort_values(['txn_date', 'psp'])[['txn_date', 'psp', 'txn_id', 'recon_result', 'break_amount_rub']].tail(10)"""),
md("## 3. Контроль балансов на PSP\nДельта = фактический баланс из выписки PSP − ожидаемый по учёту. Порог эскалации: 50 000 ₽ по модулю."),
code("""balances['delta_rub'] = (balances.actual_balance_rub - balances.expected_balance_rub).round(2)
delta = balances.pivot(index='balance_date', columns='psp', values='delta_rub')
ax = delta.plot(figsize=(10, 4), color=[COLORS[c] for c in delta.columns], lw=2)
for y in (50000, -50000):
    ax.axhline(y, color='#D14343', ls='--', lw=1)
ax.set_title('Дельта баланса по дням, ₽', loc='left', fontweight='bold')
ax.set_xlabel(''); ax.legend(frameon=False, ncol=3)
plt.tight_layout(); plt.savefig(CHARTS / 'balance_delta.png'); plt.show()

balances[balances.delta_rub.abs() > 50000][['balance_date', 'psp', 'delta_rub']]"""),
md("""**Вывод.** У PSP Beta разовый провал 9–10 сентября, на следующий день дельта вернулась к норме: похоже на задержку зачисления. У PSP Gamma с 14 сентября дельта стабильно уходит в минус: это систематическая недоплата, по времени совпадающая со всплеском расхождений по комиссиям."""),
md("## 4. Отчёт для трейдеров"),
code("""report = pd.read_sql('''
    SELECT psp,
           ROUND(100.0 * SUM(successful) / SUM(transactions), 1) AS success_rate_pct,
           ROUND(SUM(volume_rub), 0)                             AS volume_rub,
           ROUND(SUM(fee_rub), 0)                                AS fee_rub,
           ROUND(100.0 * SUM(fee_rub) / SUM(volume_rub), 2)      AS effective_fee_pct
    FROM payments_weekly GROUP BY psp ORDER BY effective_fee_pct''', con)
report"""),
code("""fig, axes = plt.subplots(1, 2, figsize=(11, 4))
vol = payments.pivot_table(index='psp', columns='type', values='volume_rub', aggfunc='sum') / 1e6
vol[['deposit', 'withdrawal']].plot(kind='bar', stacked=True, ax=axes[0], rot=0, color=['#3BA272', '#F08A24'])
axes[0].set_title('Оборот по PSP, млн ₽', loc='left', fontweight='bold'); axes[0].set_xlabel('')
axes[0].legend(['депозиты', 'выводы'], frameon=False)

by_country = payments.groupby('country')[['successful', 'transactions']].sum()
(100 * by_country.successful / by_country.transactions).sort_values().plot(kind='barh', ax=axes[1], color='#2F6FDE')
axes[1].set_title('Доля успешных платежей по странам, %', loc='left', fontweight='bold')
axes[1].set_xlim(80, 92); axes[1].set_ylabel('')
plt.tight_layout(); plt.savefig(CHARTS / 'payments_report.png'); plt.show()"""),
md("""**Выводы для стейкхолдеров**
- PSP Alfa — самый дешёвый и надёжный провайдер: больше всего оборота и самая низкая эффективная комиссия.
- PSP Gamma почти в 1,6 раза дороже Alfa и теряет каждую пятую транзакцию: стоит пересмотреть долю трафика или условия договора.
- В Нигерии самая низкая доля успешных платежей: отдельно разобрать причины отказов."""),
]

nb = nbf.v4.new_notebook(cells=cells, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
                                                  "language_info": {"name": "python"}})
out = Path(__file__).resolve().parent.parent / "notebooks" / "psp_reconciliation.ipynb"
nbf.write(nb, out)
print("written", out)
