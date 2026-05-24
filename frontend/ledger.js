const API = (() => {
  const explicit = document.querySelector('meta[name="api-base"]')?.content?.trim();
  if (explicit) return explicit;
  const port = document.querySelector('meta[name="api-port"]')?.content?.trim();
  if (port) return `${window.location.protocol}//${window.location.hostname}:${port}`;
  return window.location.origin;
})();
const $ = s => document.querySelector(s);
const themeButtons = [...document.querySelectorAll('[data-theme-choice]')];
const incomeTotal = $('#incomeTotal'), expenseTotal = $('#expenseTotal'), netTotal = $('#netTotal'), ledgerCount = $('#ledgerCount');
const incomeLabel = $('#incomeLabel'), expenseLabel = $('#expenseLabel'), netLabel = $('#netLabel'), countLabel = $('#countLabel');
const monthIncomeTotal = $('#monthIncomeTotal'), monthExpenseTotal = $('#monthExpenseTotal'), monthNetTotal = $('#monthNetTotal'), topExpenseCategory = $('#topExpenseCategory');
const ledgerList = $('#ledgerList'), ledgerTrend = $('#ledgerTrend'), ledgerPie = $('#ledgerPie'), ledgerLegend = $('#ledgerLegend');
const monthlyCategoryRank = $('#monthlyCategoryRank'), monthlyOverview = $('#monthlyOverview');
const pieRangeLabel = $('#pieRangeLabel'), pieCustomRange = $('#pieCustomRange'), pieStartDate = $('#pieStartDate'), pieEndDate = $('#pieEndDate'), pieApplyBtn = $('#pieApplyBtn');
const pieRangeButtons = [...document.querySelectorAll('#pieRangeControl [data-range]')];
const pieDirectionButtons = [...document.querySelectorAll('#pieDirectionControl [data-direction]')];
const pieDirectionControl = $('#pieDirectionControl');
let currentPieRange = 'today';
let currentPieDirection = 'expense';
let currentPieData = { expense: null, income: null };
const LEDGER_COLORS = { '支出 · 餐饮':'#fb7185', '支出 · 交通':'#38bdf8', '支出 · 购物':'#f59e0b', '支出 · 住房':'#8b5cf6', '支出 · 娱乐':'#10b981', '支出 · 医疗':'#ef4444', '支出 · 学习':'#5e6ad2', '支出 · 社交':'#ec4899', '收入 · 工资':'#22c55e', '收入 · 兼职':'#14b8a6', '收入 · 报销':'#84cc16', '收入 · 退款':'#06b6d4', '收入 · 转账':'#6366f1', '餐饮':'#fb7185', '交通':'#38bdf8', '购物':'#f59e0b', '住房':'#8b5cf6', '娱乐':'#10b981', '医疗':'#ef4444', '学习':'#5e6ad2', '社交':'#ec4899', '工资':'#22c55e', '兼职':'#14b8a6', '报销':'#84cc16', '退款':'#06b6d4', '转账':'#6366f1', '其他':'#94a3b8', '其他收入':'#94a3b8' };

function resolveTheme(choice){ return choice==='light'||choice==='dark' ? choice : (matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'); }
function applyTheme(choice){ document.documentElement.dataset.theme=choice; document.documentElement.dataset.resolvedTheme=resolveTheme(choice); localStorage.setItem('studyflow-theme',choice); themeButtons.forEach(b=>b.classList.toggle('active',b.dataset.themeChoice===choice)); }
function escapeHtml(v){ return String(v??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[ch])); }
function formatMoney(v){ return `¥${Number(v||0).toFixed(2)}`; }
async function api(path, options={}){ const res=await fetch(`${API}${path}`,{headers:{'Content-Type':'application/json',...(options.headers||{})},...options}); if(!res.ok) throw new Error(`${path} ${res.status}`); return res.json(); }

function renderLedgerSummary(data){
  const label = data.label || '今日';
  incomeLabel.textContent = `${label}收入`;
  expenseLabel.textContent = `${label}支出`;
  netLabel.textContent = `${label}净额`;
  countLabel.textContent = `${label}笔数`;
  incomeTotal.textContent=formatMoney(data.income_total);
  expenseTotal.textContent=formatMoney(data.expense_total);
  netTotal.textContent=formatMoney(data.net_total);
  ledgerCount.textContent=String((data.expense_count||0)+(data.income_count||0));
}
function renderMonthSummary(data){ monthIncomeTotal.textContent=formatMoney(data.income_total); monthExpenseTotal.textContent=formatMoney(data.expense_total); monthNetTotal.textContent=formatMoney(data.net_total); topExpenseCategory.textContent=data.top_expense_category || '暂无'; }
function renderLedgerList(items){ if(!items.length){ ledgerList.className='list empty'; ledgerList.textContent='暂无记账记录。'; return; } ledgerList.className='list'; ledgerList.innerHTML=items.map(item=>`<article class="item"><div class="item-title">${escapeHtml(item.summary)}</div><div class="item-meta">${item.direction==='income'?'收入':'支出'} · ${escapeHtml(item.category)} · ${formatMoney(item.amount)} · ${escapeHtml(item.created_at)}</div><div class="item-meta">${escapeHtml(item.raw_text)}</div></article>`).join(''); }
function renderLedgerTrend(days){ if(!days.length){ ledgerTrend.className='list empty'; ledgerTrend.textContent='暂无趋势数据。'; return; } const active=days.filter(d => d.expense_total || d.income_total).slice(-7).reverse(); const items=active.length ? active : days.slice(-7).reverse(); ledgerTrend.className='list'; ledgerTrend.innerHTML=items.map(d=>`<article class="item"><div class="item-title">${escapeHtml(d.date)}</div><div class="item-meta">收入 ${formatMoney(d.income_total)} · 支出 ${formatMoney(d.expense_total)} · 净额 ${formatMoney(d.net_total)}</div></article>`).join(''); }
function updatePieRangeUI(){ pieRangeButtons.forEach(btn=>btn.classList.toggle('active', btn.dataset.range===currentPieRange)); pieCustomRange.classList.toggle('hidden', currentPieRange!=='custom'); }
function updatePieDirectionUI(){
  pieDirectionButtons.forEach(btn=>btn.classList.toggle('active', btn.dataset.direction===currentPieDirection));
  if(pieDirectionControl) pieDirectionControl.dataset.direction = currentPieDirection;
}
function getPieQuery(){ if(currentPieRange==='custom'){ const start=pieStartDate.value; const end=pieEndDate.value; if(!start || !end) throw new Error('请先选择开始和结束日期'); return `range=custom&start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`; } return `range=${encodeURIComponent(currentPieRange)}`; }
function normalizePieBreakdown(data, direction){
  const label = direction === 'income' ? '入账' : '出账';
  return {
    ...data,
    direction,
    direction_label: label,
    items: (data.items || []).map(item => ({...item, kind: direction}))
  };
}
function polarToCartesian(cx, cy, r, angle){
  const rad = (angle - 90) * Math.PI / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}
function donutArcPath(cx, cy, outerR, innerR, startAngle, endAngle){
  const largeArc = endAngle - startAngle > 180 ? 1 : 0;
  const outerStart = polarToCartesian(cx, cy, outerR, startAngle);
  const outerEnd = polarToCartesian(cx, cy, outerR, endAngle);
  const innerEnd = polarToCartesian(cx, cy, innerR, endAngle);
  const innerStart = polarToCartesian(cx, cy, innerR, startAngle);
  return [
    `M ${outerStart.x} ${outerStart.y}`,
    `A ${outerR} ${outerR} 0 ${largeArc} 1 ${outerEnd.x} ${outerEnd.y}`,
    `L ${innerEnd.x} ${innerEnd.y}`,
    `A ${innerR} ${innerR} 0 ${largeArc} 0 ${innerStart.x} ${innerStart.y}`,
    'Z'
  ].join(' ');
}
function renderLedgerPie(data){
  const items=(data.items||[]).filter(i => Number(i.amount||0) > 0);
  const total=Number(data.total_amount||0);
  ledgerPie.style.backgroundImage = 'none';
  ledgerPie.style.backgroundColor = total > 0 ? 'transparent' : 'rgba(140,149,159,0.16)';
  if(total > 0 && items.length){
    let start=0;
    const paths = items.map((i, idx)=>{
      const deg = Number(i.amount||0) / total * 360;
      const end = start + deg;
      const color = LEDGER_COLORS[i.category] || '#94a3b8';
      const mid = start + deg / 2;
      const shift = polarToCartesian(0, 0, 5, mid);
      const labelPoint = polarToCartesian(140, 140, 150, mid);
      const safeCategory = escapeHtml(i.category);
      const safeAmount = escapeHtml(formatMoney(i.amount));
      const safePercent = escapeHtml(`${i.percent}%`);
      const path = donutArcPath(140, 140, 132, 62, start, Math.min(end, 359.999));
      start = end;
      return `<g class="donut-segment-group" tabindex="0" aria-label="${safeCategory} ${safeAmount} ${safePercent}"><path class="donut-segment" d="${path}" fill="${color}" style="--tx:${shift.x.toFixed(2)}px;--ty:${shift.y.toFixed(2)}px"></path><g class="donut-hover-label" transform="translate(${labelPoint.x.toFixed(2)} ${labelPoint.y.toFixed(2)})"><rect x="-56" y="-23" width="112" height="46" rx="12"></rect><text y="-4"><tspan>${safeCategory}</tspan></text><text y="14"><tspan>${safePercent} · ${safeAmount}</tspan></text></g></g>`;
    }).join('');
    ledgerPie.innerHTML = `<svg class="donut-svg" viewBox="0 0 280 280" role="img" aria-label="${escapeHtml(data.label || '当前范围')}收支分类">${paths}</svg><div class="donut-center"><b>${Number(total).toFixed(total >= 100 ? 0 : 2).replace(/\.00$/,'')}</b><span>¥</span></div>`;
  } else {
    ledgerPie.innerHTML=`<div class="donut-center"><b>0</b><span>¥</span></div>`;
  }
  const label = data.direction_label || (data.direction === 'income' ? '入账' : '出账');
  pieRangeLabel.textContent = data.label ? `${data.label}${label}分类` : `${label}分类`;
  ledgerLegend.innerHTML=items.length
    ? items.map(i=>`<div><span style="background:${LEDGER_COLORS[i.category] || '#94a3b8'}"></span><b>${escapeHtml(i.category)}</b><em>${formatMoney(i.amount)} · ${i.percent}%</em></div>`).join('')
    : `<div class="empty">${escapeHtml(data.label || '当前范围')}还没有${escapeHtml(label)}分类数据。</div>`;
}
function renderMonthlyCategoryRank(data){
  const items = data.items || [];
  if(!items.length){ monthlyCategoryRank.className='list empty'; monthlyCategoryRank.textContent='暂无月度分类数据。'; return; }
  monthlyCategoryRank.className='list';
  monthlyCategoryRank.innerHTML = items.map((item, idx)=>`<article class="item"><div class="item-title">#${idx+1} ${escapeHtml(item.category)}</div><div class="item-meta">${formatMoney(item.amount)} · ${item.percent}%</div></article>`).join('');
}
function renderMonthlyOverview(data){
  const months = data.months || [];
  if(!months.length){ monthlyOverview.className='list empty'; monthlyOverview.textContent='暂无月度汇总。'; return; }
  monthlyOverview.className='list';
  monthlyOverview.innerHTML = months.slice().reverse().map(item=>`<article class="item"><div class="item-title">${escapeHtml(item.month)}</div><div class="item-meta">收入 ${formatMoney(item.income_total)} · 支出 ${formatMoney(item.expense_total)} · 净额 ${formatMoney(item.net_total)}</div><div class="item-meta">支出第一类：${escapeHtml(item.top_expense_category || '暂无')}</div></article>`).join('');
}

async function loadLedger(){
  const pieQuery = getPieQuery();
  const [summary,records,expensePie,incomePie,days,monthSummary,monthCategories,monthOverview] = await Promise.all([
    api(`/api/ledger/summary/range?${pieQuery}`),
    api('/api/ledger/records?limit=12'),
    api(`/api/ledger/stats/category-breakdown?direction=expense&${pieQuery}`),
    api(`/api/ledger/stats/category-breakdown?direction=income&${pieQuery}`),
    api('/api/ledger/stats/daily?days=14'),
    api('/api/ledger/summary/month'),
    api('/api/ledger/stats/monthly-categories?direction=expense'),
    api('/api/ledger/stats/monthly-overview?months=6')
  ]);
  currentPieData = { expense: expensePie, income: incomePie };
  const activePie = normalizePieBreakdown(currentPieData[currentPieDirection] || expensePie, currentPieDirection);
  renderLedgerSummary(summary);
  renderMonthSummary(monthSummary);
  renderLedgerList(records.items);
  renderLedgerPie(activePie);
  renderLedgerTrend(days.days);
  renderMonthlyCategoryRank(monthCategories);
  renderMonthlyOverview(monthOverview);
}

async function handlePieRangeChange(nextRange){
  currentPieRange = nextRange;
  updatePieRangeUI();
  if(currentPieRange==='custom') return;
  try {
    await loadLedger();
  } catch (err) {
    pieRangeLabel.textContent = `${nextRange} 切换失败`;
    ledgerLegend.innerHTML = `<div class="empty">${escapeHtml(err.message)}</div>`;
  }
}

async function handlePieDirectionChange(nextDirection){
  currentPieDirection = nextDirection === 'income' ? 'income' : 'expense';
  updatePieDirectionUI();
  const cached = currentPieData[currentPieDirection];
  if(cached){
    renderLedgerPie(normalizePieBreakdown(cached, currentPieDirection));
    return;
  }
  try {
    await loadLedger();
  } catch (err) {
    pieRangeLabel.textContent = '方向切换失败';
    ledgerLegend.innerHTML = `<div class="empty">${escapeHtml(err.message)}</div>`;
  }
}

$('#ledgerRefreshBtn').addEventListener('click', loadLedger);
pieRangeButtons.forEach(btn=>btn.addEventListener('click', ()=>handlePieRangeChange(btn.dataset.range)));
pieDirectionButtons.forEach(btn=>btn.addEventListener('click', ()=>handlePieDirectionChange(btn.dataset.direction)));
pieApplyBtn.addEventListener('click', async ()=>{
  try {
    await loadLedger();
  } catch (err) {
    pieRangeLabel.textContent = '自定义范围加载失败';
    ledgerLegend.innerHTML = `<div class="empty">${escapeHtml(err.message)}</div>`;
  }
});
themeButtons.forEach(btn=>btn.addEventListener('click',()=>applyTheme(btn.dataset.themeChoice))); matchMedia('(prefers-color-scheme: dark)').addEventListener('change',()=>{if((localStorage.getItem('studyflow-theme')||'auto')==='auto') applyTheme('auto');});
applyTheme(localStorage.getItem('studyflow-theme')||'auto'); updatePieRangeUI(); updatePieDirectionUI(); loadLedger().catch(err=>{ledgerList.className='list empty';ledgerList.textContent=`加载失败：${err.message}`;});
