/**
 * RFM 客户分群 — 计算 + 渲染
 * ===========================
 * 职责：RFM 相关的一切——数据计算、分群卡片、条形图、佚名记录。
 *
 * 依赖：config.js 必须先加载（CONFIG 在全局作用域）。
 * 输出：全局函数，供 index.html 里的主脚本调用。
 */

/* ======================== 工具函数 ======================== */
function num(n) {
  return Math.round(n).toLocaleString('en-US');
}

function pct(x, d) {
  d = d || 1;
  return (x * 100).toFixed(d) + '%';
}

/* ======================== RFM 数据计算 ======================== */
function computeRfmData() {
  var C = CONFIG;
  var active   = C.freqMembers + C.midMembers + C.onceMembers;
  var sleeping = C.totalMembers - active;
  var perCapita = Math.round(C.annualRevenueWan * 10000 / active);
  var convertible = C.onceMembers + C.midMembers;
  var pyMax = Math.max(sleeping, C.freqMembers, C.midMembers, C.onceMembers);

  // RFM 分群
  var rfmDisplay = C.rfmSegments.slice();
  var rfmKnownSum = C.rfmSegments.reduce(function(s, x) { return s + (x.members || 0); }, 0);
  var anonCount = C.rfmAnonymous.records || 0;
  var rfmOther = active - rfmKnownSum - anonCount;
  if (rfmOther > 0) {
    rfmDisplay.push({
      name: "其余分群(待补充)", members: rfmOther, color: "#e2e8f0", placeholder: true,
      define: "尚未填入的分群。把人数补进 CONFIG 的 rfmSegments 后,此占位会自动消失。", action: "—"
    });
  }
  var rfmTotal = rfmKnownSum;
  var rfmRevTotal = C.rfmSegments.reduce(function(s, x) { return s + (x.revenueYuan || 0); }, 0);
  var rfmMax = Math.max.apply(null, rfmDisplay.map(function(x) { return x.members; }));
  var topShare = C.rfmSegments[0].revenueYuan / rfmRevTotal;

  return {
    active: active,
    sleeping: sleeping,
    perCapita: perCapita,
    convertible: convertible,
    pyMax: pyMax,
    rfmDisplay: rfmDisplay,
    rfmKnownSum: rfmKnownSum,
    rfmTotal: rfmTotal,
    rfmRevTotal: rfmRevTotal,
    rfmMax: rfmMax,
    topShare: topShare,
    anonCount: anonCount
  };
}

/* ======================== RFM HTML 构建 ======================== */
function buildRfmBars(rfmDisplay, rfmMax) {
  return rfmDisplay.map(function(s) {
    return '<div class="hbar-row">'
      + '<div class="hbar-label">' + s.name + '</div>'
      + '<div class="hbar-track"><div class="hbar-fill" style="width:' + pct(s.members / rfmMax, 1) + ';background:' + s.color + '"></div></div>'
      + '<div class="hbar-val">' + num(s.members) + '</div></div>';
  }).join('');
}

function buildRfmCards(rfmDisplay, rfmRevTotal) {
  var rfmTotal = rfmDisplay.reduce(function(s, x) { return s + x.members; }, 0);
  return rfmDisplay.map(function(s) {
    var tags = [];
    if (s.r) tags.push('<span class="rfm-tag" style="background:#eff6ff;color:#2563eb">R 最近 · ' + s.r + '</span>');
    if (s.f) tags.push('<span class="rfm-tag" style="background:#fffbeb;color:#d97706">F 频率 · ' + s.f + '</span>');
    if (s.m) tags.push('<span class="rfm-tag" style="background:#ecfdf5;color:#059669">M 金额 · ' + s.m + '</span>');
    var chips = [];
    if (s.revenueYuan != null)
      chips.push('<span class="money-chip">实付合计 <b style="color:#059669">¥' + num(s.revenueYuan) + '</b></span>');
    if (rfmRevTotal > 0 && s.revenueYuan != null)
      chips.push('<span class="money-chip">占营收 <b style="color:#d97706">' + pct(s.revenueYuan / rfmRevTotal, 1) + '</b></span>');
    if (s.avgPerVisit != null)
      chips.push('<span class="money-chip">每次到店均消 <b style="color:#2563eb">¥' + num(s.avgPerVisit) + '</b></span>');
    return '<div class="rfm-seg" style="border-left-color:' + s.color + (s.placeholder ? ';background:#f8fafc' : '') + '">'
      + '<div class="sh"><span class="sn">' + s.name + '</span>'
      + '<span class="scount">' + num(s.members) + ' 人 · ' + pct(s.members / rfmTotal, 1) + '</span></div>'
      + (tags.length ? '<div>' + tags.join('') + '</div>' : '')
      + (chips.length ? '<div class="money-row">' + chips.join('') + '</div>' : '')
      + '<div class="sd">📌 <b>分类依据:</b>' + s.define + '</div>'
      + (s.action !== '—' ? '<div class="sa">🎯 <b>运营动作:</b>' + s.action + '</div>' : '')
      + '</div>';
  }).join('');
}

function buildAnonCard() {
  var C = CONFIG;
  return '<div class="rfm-seg" style="border-left-color:#94a3b8;background:#f8fafc">'
    + '<div class="sh"><span class="sn">🎭 佚名客户(未识别)</span>'
    + '<span class="scount">' + num(C.rfmAnonymous.records) + ' 条合并记录 · ¥' + num(C.rfmAnonymous.revenueYuan) + ' 累计消费</span></div>'
    + '<div class="sd">📌 <b>为什么单列:</b>' + C.rfmAnonymous.note + '</div>'
    + '<div class="sa">🎯 <b>处理方式:</b>不参与上面的 RFM 打分与分群统计,仅在此单独保留记录。若日后要对这群人做精准营销,需先在系统里把会员名规范化(去掉表情/特殊符号)后重新识别拆分。</div>'
    + '</div>';
}
