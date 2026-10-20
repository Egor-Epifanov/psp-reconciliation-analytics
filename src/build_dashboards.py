"""
Собирает интерактивные дашборды в docs/ для GitHub Pages:
  docs/index.html      — навигация
  docs/recon.html      — ежедневная сверка: match rate, расхождения, журнал
  docs/balances.html   — контроль балансов на PSP
  docs/payments.html   — платёжный отчёт для трейдеров

Данные считаются из data/*.csv тем же SQL, что и в sql/reconciliation.sql.
Запуск: python src/build_dashboards.py
"""
import json
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA, DOCS = ROOT / "data", ROOT / "docs"
DOCS.mkdir(exist_ok=True)

ledger = pd.read_csv(DATA / "ledger.csv")
psp_report = pd.read_csv(DATA / "psp_report.csv")
balances = pd.read_csv(DATA / "balances.csv")
payments = pd.read_csv(DATA / "payments_weekly.csv")

con = sqlite3.connect(":memory:")
ledger.to_sql("ledger", con, index=False)
psp_report.to_sql("psp_report", con, index=False)
recon = pd.read_sql((ROOT / "sql" / "reconciliation.sql").read_text(encoding="utf-8"), con)

TYPE_RU = {"status": "Статус", "amount": "Сумма", "fee": "Комиссия",
           "missing_in_psp": "Нет у PSP", "missing_in_ledger": "Нет в учёте"}
recon["ok"] = recon.recon_result == "matched"
daily = recon.groupby(["txn_date", "psp"]).agg(n=("txn_id", "size"), ok=("ok", "sum")).reset_index()
breaks = recon[~recon.ok].sort_values(["txn_date", "psp"])
recon_data = {
    "days": sorted(recon.txn_date.unique().tolist()),
    "daily": daily.to_dict("records"),
    "breaks": [dict(date=r.txn_date, psp=r.psp, id=r.txn_id, type=TYPE_RU[r.recon_result],
                    amount=float(r.break_amount_rub)) for r in breaks.itertuples()],
}
balances["delta"] = (balances.actual_balance_rub - balances.expected_balance_rub).round(2)
bal_data = balances.rename(columns={"balance_date": "date"})[["date", "psp", "expected_balance_rub", "actual_balance_rub", "delta"]].to_dict("records")
pay_data = payments.to_dict("records")

HEAD = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
:root{{--bg:#fff;--fg:#1F2430;--muted:#6B7280;--line:#E5E7EB;--card:#F7F8FA;--alfa:#2F6FDE;--beta:#8B5CF6;--gamma:#F08A24;--bad:#D14343;--good:#3BA272}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 Inter,"Segoe UI",Arial,sans-serif}}
.wrap{{max-width:1100px;margin:0 auto;padding:20px 16px 32px}}
h1{{font-size:20px;margin:0 0 4px}}.sub{{color:var(--muted);margin:0 0 16px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin-bottom:16px}}
.kpi{{background:var(--card);border-radius:10px;padding:12px 14px}}.kpi b{{display:block;font-size:22px;font-variant-numeric:tabular-nums}}.kpi span{{color:var(--muted);font-size:12px}}
.filters{{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px}}
.chip{{border:1px solid var(--line);background:#fff;border-radius:999px;padding:6px 12px;cursor:pointer;font:inherit;display:flex;gap:6px;align-items:center}}
.chip i{{width:10px;height:10px;border-radius:50%;display:inline-block}}.chip.off{{opacity:.4}}
.chip:focus-visible{{outline:2px solid var(--alfa);outline-offset:2px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:14px}}
.card{{border:1px solid var(--line);border-radius:12px;padding:14px;min-width:0}}.card h2{{font-size:15px;margin:0 0 2px}}.card p{{color:var(--muted);margin:0 0 10px;font-size:12px}}
.chart{{position:relative;height:280px}}
table{{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums;font-size:13px}}th,td{{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line)}}th{{color:var(--muted);font-weight:500}}
.scroll{{max-height:320px;overflow:auto}}.tag{{padding:2px 8px;border-radius:999px;font-size:12px;background:var(--card)}}
.hint{{color:var(--muted);font-size:12px;margin-top:6px}}
.foot{{color:var(--muted);font-size:12px;margin-top:18px}}a{{color:var(--alfa)}}
@media (max-width:520px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><div class="wrap">"""
FOOT = """<div class="foot">Собственный проект · Егор Епифанов · <a href="https://github.com/Egor-Epifanov/psp-reconciliation-analytics" target="_blank">код на GitHub</a></div></div>
<script>
const COLORS={'PSP Alfa':'#2F6FDE','PSP Beta':'#8B5CF6','PSP Gamma':'#F08A24'};const PSP=Object.keys(COLORS);
let active=new Set(PSP);
function chips(onChange){const el=document.getElementById('filters');PSP.forEach(p=>{const b=document.createElement('button');b.className='chip';b.innerHTML=`<i style="background:${COLORS[p]}"></i>${p}`;b.onclick=()=>{if(active.has(p)){if(active.size>1)active.delete(p)}else active.add(p);b.classList.toggle('off',!active.has(p));onChange()};el.appendChild(b)})}
Chart.defaults.locale='ru-RU';const fmt=(v,d=0)=>v.toLocaleString('ru-RU',{minimumFractionDigits:d,maximumFractionDigits:d});
Chart.defaults.font.family='Inter,"Segoe UI",Arial,sans-serif';Chart.defaults.color='#6B7280';Chart.defaults.plugins.legend.display=false;
</script>"""


def page(name, title, body, script, data):
    html = HEAD.format(title=title) + body + FOOT + f"<script>const D={json.dumps(data, ensure_ascii=False)};\n{script}</script></body></html>"
    (DOCS / name).write_text(html, encoding="utf-8")
    print(name, len(html) // 1024, "KB")


page("recon.html", "Сверка с PSP", """
<h1>Ежедневная сверка: учёт против отчётов PSP</h1><p class="sub">Сентябрь 2026 · нажмите на PSP, чтобы скрыть или показать его · нажмите на столбец, чтобы отфильтровать журнал</p>
<div id="filters" class="filters"></div>
<div class="kpis"><div class="kpi"><b id="k1"></b><span>транзакций</span></div><div class="kpi"><b id="k2"></b><span>расхождений</span></div><div class="kpi"><b id="k3"></b><span>match rate</span></div><div class="kpi"><b id="k4"></b><span>сумма расхождений</span></div></div>
<div class="grid"><div class="card"><h2>Match rate по дням, %</h2><p>Пунктир: порог 99%</p><div class="chart"><canvas id="c1"></canvas></div></div>
<div class="card"><h2>Расхождения по PSP и типу</h2><p>Клик по столбцу фильтрует журнал ниже</p><div class="chart"><canvas id="c2"></canvas></div></div></div>
<div class="card" style="margin-top:14px"><h2>Журнал расхождений</h2><p id="jt">Все расхождения</p><div class="scroll"><table><thead><tr><th>Дата</th><th>PSP</th><th>Транзакция</th><th>Тип</th><th>Сумма, ₽</th></tr></thead><tbody id="tb"></tbody></table></div><div class="hint" id="reset" style="display:none"><a href="#" onclick="jf=null;draw();return false">Показать все</a></div></div>
""", """
const TYPES=['Статус','Сумма','Комиссия','Нет у PSP','Нет в учёте'],TC=['#D14343','#F08A24','#E5B800','#2F6FDE','#8B5CF6'];let jf=null;
const c1=new Chart(document.getElementById('c1'),{type:'line',data:{labels:D.days.map(d=>d.slice(8)),datasets:[]},options:{maintainAspectRatio:false,interaction:{mode:'index',intersect:false},scales:{y:{min:92,max:100}},plugins:{tooltip:{callbacks:{label:c=>`${c.dataset.label}: ${fmt(c.parsed.y,2)}%`}}}}});
const c2=new Chart(document.getElementById('c2'),{type:'bar',data:{labels:[],datasets:[]},options:{maintainAspectRatio:false,scales:{x:{stacked:true},y:{stacked:true}},plugins:{legend:{display:true,position:'bottom'}},onClick:(e,els)=>{if(!els.length)return;const el=els[0];jf={psp:c2.data.labels[el.index],type:TYPES[el.datasetIndex]};draw()}}});
function draw(){const rows=D.daily.filter(r=>active.has(r.psp));const n=rows.reduce((s,r)=>s+r.n,0),ok=rows.reduce((s,r)=>s+r.ok,0);
const br=D.breaks.filter(b=>active.has(b.psp));k1.textContent=fmt(n);k2.textContent=fmt(n-ok);k3.textContent=fmt(100*ok/n,2)+'%';k4.textContent=fmt(br.reduce((s,b)=>s+b.amount,0))+' ₽';
c1.data.datasets=[...PSP.filter(p=>active.has(p)).map(p=>({label:p,borderColor:COLORS[p],backgroundColor:COLORS[p],pointRadius:2,borderWidth:2,tension:.2,data:D.days.map(d=>{const r=D.daily.find(x=>x.txn_date==d&&x.psp==p);return 100*r.ok/r.n})})),{label:'порог',data:D.days.map(()=>99),borderColor:'#D14343',borderDash:[5,4],pointRadius:0,borderWidth:1}];c1.update();
const ps=PSP.filter(p=>active.has(p));c2.data.labels=ps;c2.data.datasets=TYPES.map((t,i)=>({label:t,backgroundColor:TC[i],data:ps.map(p=>br.filter(b=>b.psp==p&&b.type==t).length)}));c2.update();
const list=br.filter(b=>!jf||(b.psp==jf.psp&&b.type==jf.type));jt.textContent=jf?`${jf.psp} · ${jf.type} · ${list.length} шт.`:`Все расхождения · ${list.length} шт.`;reset.style.display=jf?'block':'none';
tb.innerHTML=list.map(b=>`<tr><td>${b.date}</td><td><span class="tag" style="color:${COLORS[b.psp]}">${b.psp}</span></td><td>${b.id}</td><td>${b.type}</td><td>${fmt(b.amount,2)}</td></tr>`).join('')}
chips(()=>{jf=null;draw()});draw();
""", recon_data)

page("balances.html", "Балансы PSP", """
<h1>Контроль балансов на PSP</h1><p class="sub">Дельта = фактический баланс из выписки PSP − ожидаемый по учёту · порог эскалации ±50 000 ₽ · нажмите на PSP, чтобы скрыть или показать его</p>
<div id="filters" class="filters"></div>
<div class="kpis"><div class="kpi"><b id="k1"></b><span>дней выше порога</span></div><div class="kpi"><b id="k2"></b><span>худшая дельта</span></div><div class="kpi"><b id="k3"></b><span>дельта на 30 сентября</span></div></div>
<div class="card"><h2>Дельта баланса по дням, ₽</h2><p>Наведите на точку, чтобы увидеть ожидание и факт</p><div class="chart" style="height:340px"><canvas id="c1"></canvas></div></div>
<div class="card" style="margin-top:14px"><h2>Дни выше порога</h2><table><thead><tr><th>Дата</th><th>PSP</th><th>Ожидание, ₽</th><th>Факт, ₽</th><th>Дельта, ₽</th></tr></thead><tbody id="tb"></tbody></table></div>
""", """
const days=[...new Set(D.map(r=>r.date))];
const c1=new Chart(document.getElementById('c1'),{type:'line',data:{labels:days.map(d=>d.slice(8)),datasets:[]},options:{maintainAspectRatio:false,interaction:{mode:'nearest',intersect:false},plugins:{tooltip:{callbacks:{label:c=>{const r=D.find(x=>x.psp==c.dataset.label&&x.date==days[c.dataIndex]);return r?`${r.psp}: дельта ${fmt(r.delta)}&nbsp;₽ (ожидание ${fmt(r.expected_balance_rub)} · факт ${fmt(r.actual_balance_rub)})`:''}}}}}});
function draw(){const rows=D.filter(r=>active.has(r.psp));const over=rows.filter(r=>Math.abs(r.delta)>50000);const worst=rows.reduce((a,b)=>b.delta<a.delta?b:a);
k1.textContent=over.length;k2.textContent=fmt(worst.delta)+' ₽';k2.title=worst.psp+' · '+worst.date;k3.textContent=PSP.filter(p=>active.has(p)).map(p=>fmt(D.filter(r=>r.psp==p).at(-1).delta)).join(' / ')+' ₽';
c1.data.datasets=[...PSP.filter(p=>active.has(p)).map(p=>({label:p,borderColor:COLORS[p],backgroundColor:COLORS[p],pointRadius:2,borderWidth:2,tension:.2,data:D.filter(r=>r.psp==p).map(r=>r.delta)})),{label:'+50 000',data:days.map(()=>50000),borderColor:'#D14343',borderDash:[5,4],pointRadius:0,borderWidth:1},{label:'−50 000',data:days.map(()=>-50000),borderColor:'#D14343',borderDash:[5,4],pointRadius:0,borderWidth:1}];c1.update();
tb.innerHTML=over.map(r=>`<tr><td>${r.date}</td><td><span class="tag" style="color:${COLORS[r.psp]}">${r.psp}</span></td><td>${fmt(r.expected_balance_rub)}</td><td>${fmt(r.actual_balance_rub)}</td><td style="color:#D14343">${fmt(r.delta)}</td></tr>`).join('')}
chips(draw);draw();
""", bal_data)

page("payments.html", "Платёжный отчёт", """
<h1>Платёжный отчёт для трейдеров</h1><p class="sub">Сентябрь 2026 · 3 PSP · Бразилия, Нигерия, Сербия · фильтруйте по PSP, стране и типу операции</p>
<div id="filters" class="filters"></div><div id="f2" class="filters"></div>
<div class="kpis"><div class="kpi"><b id="k1"></b><span>оборот</span></div><div class="kpi"><b id="k2"></b><span>доля успешных</span></div><div class="kpi"><b id="k3"></b><span>комиссии</span></div><div class="kpi"><b id="k4"></b><span>эффективная комиссия</span></div></div>
<div class="grid"><div class="card"><h2>Оборот по неделям, млн ₽</h2><p>Наведите на неделю, чтобы сравнить PSP</p><div class="chart"><canvas id="c1"></canvas></div></div>
<div class="card"><h2>Доля успешных и эффективная комиссия</h2><p>Столбцы: доля успешных, %. Точки: эффективная комиссия, %</p><div class="chart"><canvas id="c2"></canvas></div></div></div>
<div class="card" style="margin-top:14px"><h2>Сводка по PSP</h2><table><thead><tr><th>PSP</th><th>Транзакций</th><th>Успешных, %</th><th>Оборот, ₽</th><th>Комиссии, ₽</th><th>Эфф. комиссия</th></tr></thead><tbody id="tb"></tbody></table></div>
""", """
const COUNTRIES=['Бразилия','Нигерия','Сербия'],TYPES={deposit:'Депозиты',withdrawal:'Выводы'};let ac=new Set(COUNTRIES),at=new Set(Object.keys(TYPES));
const f2=document.getElementById('f2');
function chip2(set,key,label){const b=document.createElement('button');b.className='chip';b.textContent=label;b.onclick=()=>{if(set.has(key)){if(set.size>1)set.delete(key)}else set.add(key);b.classList.toggle('off',!set.has(key));draw()};f2.appendChild(b)}
COUNTRIES.forEach(c=>chip2(ac,c,c));Object.entries(TYPES).forEach(([k,v])=>chip2(at,k,v));
const weeks=[...new Set(D.map(r=>r.week))];
const c1=new Chart(document.getElementById('c1'),{type:'line',data:{labels:weeks.map(w=>'Нед '+w.slice(-2)),datasets:[]},options:{maintainAspectRatio:false,interaction:{mode:'index',intersect:false},scales:{y:{beginAtZero:true}},plugins:{tooltip:{callbacks:{label:c=>`${c.dataset.label}: ${fmt(c.parsed.y,1)}k&nbsp;₽`}}}}});
const c2=new Chart(document.getElementById('c2'),{data:{labels:[],datasets:[]},options:{maintainAspectRatio:false,scales:{y:{min:70,max:100,title:{display:true,text:'успешных, %'}},y2:{position:'right',min:0,max:4,grid:{display:false},title:{display:true,text:'комиссия, %'}}}}});
function agg(rows){const s=k=>rows.reduce((a,r)=>a+r[k],0);return{n:s('transactions'),ok:s('successful'),v:s('volume_rub'),f:s('fee_rub')}}
function draw(){const rows=D.filter(r=>active.has(r.psp)&&ac.has(r.country)&&at.has(r.type));const t=agg(rows);
k1.textContent=fmt(t.v)+' ₽';k2.textContent=fmt(100*t.ok/t.n,1)+'%';k3.textContent=fmt(t.f)+' ₽';k4.textContent=fmt(100*t.f/t.v,2)+'%';
const ps=PSP.filter(p=>active.has(p));
c1.data.datasets=ps.map(p=>({label:p,borderColor:COLORS[p],backgroundColor:COLORS[p],borderWidth:2.5,tension:.2,data:weeks.map(w=>agg(rows.filter(r=>r.psp==p&&r.week==w)).v/1e6)}));c1.update();
const by=ps.map(p=>agg(rows.filter(r=>r.psp==p)));c2.data.labels=ps;
c2.data.datasets=[{type:'bar',label:'Успешных, %',data:by.map(a=>100*a.ok/a.n),backgroundColor:ps.map(p=>COLORS[p]),yAxisID:'y',order:1},{type:'line',label:'Эфф. комиссия, %',data:by.map(a=>100*a.f/a.v),borderColor:'#1F2430',backgroundColor:'#1F2430',showLine:false,pointRadius:6,yAxisID:'y2',order:0}];c2.update();
tb.innerHTML=ps.map((p,i)=>{const a=by[i];return`<tr><td><span class="tag" style="color:${COLORS[p]}">${p}</span></td><td>${fmt(a.n)}</td><td>${fmt(100*a.ok/a.n,1)}</td><td>${fmt(a.v)}</td><td>${fmt(a.f)}</td><td>${fmt(100*a.f/a.v,2)}%</td></tr>`}).join('')}
chips(draw);draw();
""", pay_data)

(DOCS / "index.html").write_text(HEAD.format(title="Дашборды PSP") + """
<h1>Дашборды: сверка платежей с PSP</h1><p class="sub">Собственный проект · SQL + pandas + Chart.js</p>
<div class="grid"><a class="card" href="recon.html" style="text-decoration:none;color:inherit"><h2>Ежедневная сверка</h2><p>Match rate по дням, расхождения по PSP и типу, журнал</p></a>
<a class="card" href="balances.html" style="text-decoration:none;color:inherit"><h2>Балансы на PSP</h2><p>Ожидание против факта, порог эскалации</p></a>
<a class="card" href="payments.html" style="text-decoration:none;color:inherit"><h2>Платёжный отчёт</h2><p>Оборот, доля успешных, эффективная комиссия</p></a></div>
""" + FOOT + "</body></html>", encoding="utf-8")
print("index.html")
