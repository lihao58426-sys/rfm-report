/**
 * 图表模块 — 月度淡旺季 / 频率漏斗 / 行动优先级 / 同比
 * ======================================================
 * 职责：非 RFM 的图表计算和 HTML 渲染。
 *
 * 依赖：config.js（CONFIG）和 rfm.js（num / pct 工具函数）必须先加载。
 * 输出：全局函数，供 index.html 里的主脚本调用。
 */

/* ======================== 月度淡旺季 ======================== */
function computeMonthlyData() {
  var C = CONFIG;
  var segColor = {};
  C.rfmSegments.forEach(function(s) { segColor[s.name] = s.color; });

  function moByType(mo) {
    if (mo.byType) return { data: mo.byType, approx: false };
    var r = {}, tot = mo.total || 0;
    C.rfmSegments.forEach(function(s) { r[s.name] = tot * (C.defaultTypeRatio[s.name] || 0); });
    return { data: r, approx: true };
  }

  var moRows = C.monthly.map(function(mo) {
    var bt = moByType(mo);
    var tot = mo.total != null ? mo.total : Object.keys(bt.data).reduce(function(s, k) { return s + bt.data[k]; }, 0);
    return { m: mo.m, tot: tot, bt: bt.data, approx: bt.approx };
  });

  var moMax  = Math.max.apply(null, moRows.map(function(x) { return x.tot; }));
  var moYear = moRows.reduce(function(s, x) { return s + x.tot; }, 0);
  var anyApprox = moRows.some(function(x) { return x.approx; });

  var peak = moRows[0], low = moRows[0];
  moRows.forEach(function(x) { if (x.tot > peak.tot) peak = x; if (x.tot < low.tot) low = x; });

  var summerTot = moRows.filter(function(x) { return x.m.indexOf('7月') >= 0 || x.m.indexOf('8月') >= 0; })
    .reduce(function(s, x) { return s + x.tot; }, 0);

  // 同比
  var jun25 = moRows.find(function(x) { return x.m === '2025年6月'; });
  var jun26 = moRows.find(function(x) { return x.m === '2026年6月'; });
  var yoyJun = (jun25 && jun26 && jun25.tot > 0) ? (jun26.tot - jun25.tot) / jun25.tot : null;

  var annualYuan = C.annualRevenueWan * 10000;
  var moGap = annualYuan - moYear;

  return {
    moRows: moRows,
    moMax: moMax,
    moYear: moYear,
    anyApprox: anyApprox,
    peak: peak,
    low: low,
    summerTot: summerTot,
    jun25: jun25,
    jun26: jun26,
    yoyJun: yoyJun,
    moGap: moGap,
    segColor: segColor
  };
}

function buildMoBars(moRows, moMax, moYear, segColor) {
  var C = CONFIG;
  return moRows.map(function(x) {
    var inner = C.rfmSegments.map(function(s) {
      var v = x.bt[s.name] || 0;
      if (!v) return '';
      return '<div style="width:' + (v / x.tot * 100).toFixed(2) + '%;background:' + s.color + '"></div>';
    }).join('');
    return '<div class="hbar-row">'
      + '<div class="hbar-label" style="width:40px">' + x.m + (x.approx ? '<span style="color:#f59e0b">*</span>' : '') + '</div>'
      + '<div class="hbar-track" style="height:24px"><div class="hbar-fill" style="width:' + (x.tot / moMax * 100).toFixed(1) + '%;display:flex;overflow:hidden;border-radius:6px">' + inner + '</div></div>'
      + '<div class="hbar-val" style="width:108px;text-align:right">¥' + (x.tot / 10000).toFixed(1) + '万·' + pct(x.tot / moYear, 1) + '</div></div>';
  }).join('');
}

function buildMoLegend() {
  var C = CONFIG;
  return C.rfmSegments.map(function(s) {
    return '<div class="legend-item"><span class="dot" style="background:' + s.color + '"></span><span>' + s.name + '</span></div>';
  }).join('');
}

function buildYoyComparison(yoyJun, jun25, jun26) {
  if (yoyJun == null) return '';
  return '<div class="card">'
    + '<h2>📈 同比对比 · 同月</h2>'
    + '<div class="sub">数据首尾各含一个 6 月,正好可做同月同比,看经营方向</div>'
    + '<div class="yoy">'
    + '<div class="box"><div class="yv">¥' + (jun25.tot / 10000).toFixed(2) + '万</div><div class="yl">2025年6月</div></div>'
    + '<div class="arrow">→</div>'
    + '<div class="box"><div class="yv">¥' + (jun26.tot / 10000).toFixed(2) + '万</div><div class="yl">2026年6月</div></div>'
    + '<div class="box"><div class="delta" style="color:' + (yoyJun < 0 ? '#ef4444' : '#059669') + '">' + (yoyJun < 0 ? '▼' : '▲') + ' ' + pct(Math.abs(yoyJun), 1) + '</div><div class="yl">同比</div></div>'
    + '</div>'
    + '<div class="note" style="background:#eff6ff;border:1px solid #bfdbfe;margin-top:10px">'
    + '<span style="color:#1e3a8a"><b class="blue">注意:</b>两个 6 月均为半月(15 日截断),口径一致可比;同比' + (yoyJun < 0 ? '下滑' : '上升') + '约 ' + pct(Math.abs(yoyJun), 0) + ',建议结合天气、活动档期进一步归因。单点同比仅作方向参考,后续补齐逐月同比更可靠。</span>'
    + '</div></div>';
}

/* ======================== 行动优先级表 ======================== */
function buildActionPlan() {
  var C = CONFIG;
  return C.actionPlan.map(function(a) {
    return '<tr>'
      + '<td><span class="pri-tag" style="background:' + a.color + '">' + a.priority + '</span></td>'
      + '<td><b style="color:#1e293b">' + a.action + '</b></td>'
      + '<td>' + a.target + '</td>'
      + '<td>' + a.basis + '</td>'
      + '<td><b style="color:#059669">' + a.expect + '</b></td>'
      + '<td>' + a.owner + '</td>'
      + '</tr>';
  }).join('');
}

/* ======================== 频率漏斗 ======================== */
function buildFreqChart(active, sleeping, pyMax, convertible) {
  var C = CONFIG;
  return ''
    + '<div class="hbar-row">'
    + '<div class="hbar-label">沉睡/未激活</div>'
    + '<div class="hbar-track"><div class="hbar-fill" style="width:' + pct(sleeping / pyMax, 1) + ';background:#cbd5e1"></div></div>'
    + '<div class="hbar-val">' + num(sleeping) + '</div>'
    + '</div>'
    + '<div class="hbar-row">'
    + '<div class="hbar-label">来4次及以上</div>'
    + '<div class="hbar-track"><div class="hbar-fill" style="width:' + pct(C.freqMembers / pyMax, 1) + ';background:#f59e0b"></div></div>'
    + '<div class="hbar-val">' + num(C.freqMembers) + '</div>'
    + '</div>'
    + '<div class="hbar-row">'
    + '<div class="hbar-label">来2-3次(中间层)</div>'
    + '<div class="hbar-track"><div class="hbar-fill" style="width:' + pct(C.midMembers / pyMax, 1) + ';background:#60a5fa"></div></div>'
    + '<div class="hbar-val">' + num(C.midMembers) + '</div>'
    + '</div>'
    + '<div class="hbar-row">'
    + '<div class="hbar-label">只来1次(漏斗破口)</div>'
    + '<div class="hbar-track"><div class="hbar-fill" style="width:' + pct(C.onceMembers / pyMax, 1) + ';background:#f87171"></div></div>'
    + '<div class="hbar-val">' + num(C.onceMembers) + '</div>'
    + '</div>'
    + '<div class="legend">'
    + '<div class="legend-item"><span class="dot" style="background:#cbd5e1"></span><span><b class="dark">沉睡/未激活:</b> 近一年无消费(含已"毕业"的)</span></div>'
    + '<div class="legend-item"><span class="dot" style="background:#f59e0b"></span><span><b class="dark">来4次及以上:</b> 高频,生意的命根子</span></div>'
    + '<div class="legend-item"><span class="dot" style="background:#60a5fa"></span><span><b class="dark">来2-3次:</b> 最有提升空间的人</span></div>'
    + '<div class="legend-item"><span class="dot" style="background:#f87171"></span><span><b class="dark">只来1次:</b> 试过就走,留存失败</span></div>'
    + '</div>';
}
