"""
RFM + 客户生命周期分析引擎
==========================
读银豹 CSV → 合并清洗 → RFM 分群 → 生命周期阶段 → CLV 估算 → 留存曲线 → 月度趋势

银豹 CSV 表头：
  流水号  日期  类型  收银员  会员  导购员  商品信息  ...
  会员格式："姓名（手机号）" 或 "-"（佚名）
  日期格式：YYYY-MM-DD HH:MM:SS
"""

import csv
import logging
import re
from collections import defaultdict
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)

# ── 生命周期配置 ──
# R（距今天数）阈值
R_NEAR = 30      # 30 天内 = "近"
R_MID = 90       # 30-90 天 = "中"，超过 90 天 = "远"
# F（累计次数）阈值 — 可根据实际数据分布调整
F_LOW = 2        # ≤2 次 = "低"
F_HIGH = 6       # ≥6 次 = "高"，中间 = "中"
# 预计生命周期（年）— 卡丁车店：客户从 3 岁到 8 岁，约 5 年
LIFECYCLE_YEARS = 5

# RFM 8 类名称
SEGMENT_NAMES = [
    "重要价值客户", "重要唤回客户", "重要发展客户", "重要挽留客户",
    "一般活跃客户", "一般客户", "新客/低频客户", "流失客户",
]
SEGMENT_COLORS = {
    "重要价值客户": "#f59e0b", "重要唤回客户": "#8b5cf6",
    "重要发展客户": "#fb923c", "重要挽留客户": "#f97316",
    "一般活跃客户": "#10b981", "一般客户": "#60a5fa",
    "新客/低频客户": "#38bdf8", "流失客户": "#cbd5e1",
}


def _parse_member(raw: str) -> tuple[str, str]:
    """从 '张三（13800138000）' 拆出 (name, phone)。
    '-' 返回 ('佚名', '')。
    """
    raw = raw.strip()
    if raw == "-" or not raw:
        return "佚名", ""
    match = re.search(r"[（(](\d{5,20})[）)]", raw)  # 兼容中英文括号
    if match:
        phone = match.group(1)
        name = raw[: match.start()].strip()
        return name, phone
    # 没有手机号 → 用名字本身当 ID
    return raw, raw


def _classify_rfm(r: int, f: int, m: float, avg_r: float, avg_f: float, avg_m: float) -> str:
    """R/F/M vs 均值 → 8 类标签"""
    r_label = "近" if r < avg_r else "远"
    f_label = "高" if f >= avg_f else "低"
    m_label = "高" if m >= avg_m else "低"

    if r_label == "近" and f_label == "高" and m_label == "高":
        return "重要价值客户"
    elif r_label == "远" and f_label == "高" and m_label == "高":
        return "重要唤回客户"
    elif r_label == "近" and f_label == "低" and m_label == "高":
        return "重要发展客户"
    elif r_label == "远" and f_label == "低" and m_label == "高":
        return "重要挽留客户"
    elif r_label == "近" and f_label == "高" and m_label == "低":
        return "一般活跃客户"
    elif r_label == "远" and f_label == "高" and m_label == "低":
        return "一般客户"
    elif r_label == "近" and f_label == "低" and m_label == "低":
        return "新客/低频客户"
    else:
        return "流失客户"


def _classify_lifecycle(r: int, f: int, m: float, avg_m: float) -> str:
    """根据 R/F 精细阈值 + M 判断生命周期阶段

    新客期: 刚来，F ≤ F_LOW，R ≤ R_NEAR
    成长期: 频次在上升，F 中，R ≤ R_NEAR
    成熟期: 高频高消费，F ≥ F_HIGH 且 M ≥ avg_m，R ≤ R_NEAR
    休眠期: 曾经活跃但最近没来，F ≥ F_HIGH，R > R_NEAR
    流失期: 来得少、不来了，F ≤ F_LOW，R > R_MID
    """
    if r <= R_NEAR and f <= F_LOW:
        return "新客期"
    elif r <= R_NEAR and F_LOW < f < F_HIGH:
        return "成长期"
    elif r <= R_NEAR and f >= F_HIGH and m >= avg_m:
        return "成熟期"
    elif r > R_NEAR and f >= F_HIGH:
        return "休眠期"
    elif r > R_MID and f <= F_LOW:
        return "流失期"
    else:
        return "稳定期"  # 不属于以上极端的普通客户


def _calc_clv(member: dict, avg_annual_visits: float) -> float:
    """估算客户生命周期价值（CLV）

    CLV = 每次均消 × 年均到店次数 × 预估剩余年数
    预估剩余年数 = LIFECYCLE_YEARS × (已消费月数 / LIFECYCLE_YEARS 对应的月数) 的反比
    """
    avg_per_visit = member["avg_per_visit"]
    # 根据 F 估算年均次数：总次数 / 活跃年数（最少半年）
    months_active = max(1, (member["r"] / 30) or 1)  # 粗略估算
    annual_visits = member["f"] / max(0.5, months_active / 12)

    # 剩余生命周期 = LIFECYCLE_YEARS - 已用年数（最少留 1 年）
    years_used = min(months_active / 12, LIFECYCLE_YEARS - 1)
    years_remaining = max(1, LIFECYCLE_YEARS - years_used)

    clv = avg_per_visit * annual_visits * years_remaining
    return round(clv, 0)


def analyze(files: list) -> dict:
    """主分析函数

    Args:
        files: 上传的 CSV 文件对象列表（werkzeug FileStorage 或普通文件路径）

    Returns:
        完整分析结果 dict
    """
    # ── 第一步：读所有 CSV → 合并 → 去重复表头 ──
    all_rows = []
    headers = None
    for i, f in enumerate(files):
        # 兼容文件路径 (str) 和 FastAPI UploadFile
        if isinstance(f, str):
            fh = open(f, "r", encoding="utf-8-sig")
            reader = csv.DictReader(fh)
            close_later = True
        elif hasattr(f, 'file'):
            # FastAPI UploadFile → 读 bytes → 转字符串
            content = f.file.read()
            if isinstance(content, bytes):
                content = content.decode("utf-8-sig")
            reader = csv.DictReader(content.splitlines())
            close_later = False
        else:
            # BytesIO / StringIO 等普通文件对象
            content = f.read()
            if isinstance(content, bytes):
                content = content.decode("utf-8-sig")
            reader = csv.DictReader(content.splitlines())
            close_later = False

        if i == 0:
            headers = reader.fieldnames
        else:
            next(reader, None)  # 跳过后三份的表头

        all_rows.extend(list(reader))
        if close_later:
            fh.close()

    if not headers:
        return {"error": "CSV 文件为空"}

    required = ["会员", "日期", "实收金额"]
    missing = [c for c in required if c not in (headers or [])]
    if missing:
        return {"error": f"缺少必要列: {', '.join(missing)}。表头: {headers}"}

    # ── 第二步：清洗 + 解析 ──
    members = defaultdict(lambda: {
        "phone": "", "name": "", "dates": [], "transactions": 0,
        "total_revenue": 0.0, "first_date": None,
        "card_pay": 0.0, "stored_card_pay": 0.0, "cash_pay": 0.0,
    })
    anonymous = {"records": 0, "revenue": 0.0, "transactions": 0}
    monthly_revenue = defaultdict(float)
    errors = []
    total_rows = 0

    for row in all_rows:
        total_rows += 1
        try:
            txn_type = row.get("类型", "").strip()
            if "退款" in txn_type or "退货" in txn_type:
                continue

            member_raw = row.get("会员", "").strip()
            date_str = row.get("日期", "").strip()
            revenue_str = row.get("实收金额", "0").strip()

            if not date_str:
                continue
            trans_date = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
            revenue = float(revenue_str) if revenue_str else 0.0
            if revenue <= 0:
                continue

            name, phone = _parse_member(member_raw)

            # 佚名
            if name == "佚名" and not phone:
                anonymous["records"] += 1
                anonymous["revenue"] += revenue
                anonymous["transactions"] += 1
                month_key = date_str[:7]
                monthly_revenue[month_key] += revenue
                continue

            # 散客
            if not member_raw:
                continue

            m = members[phone or name]
            if not m["phone"] and phone:
                m["phone"] = phone
            if not m["name"]:
                m["name"] = name
            m["dates"].append(trans_date)
            m["transactions"] += 1
            m["total_revenue"] += revenue
            if m["first_date"] is None or trans_date < m["first_date"]:
                m["first_date"] = trans_date
            m["card_pay"] += float(row.get("次卡支付", "0") or 0)
            m["stored_card_pay"] += (
                float(row.get("储值卡支付", "0") or 0)
                + float(row.get("储值本金支付", "0") or 0)
                + float(row.get("储值赠送支付", "0") or 0)
            )
            m["cash_pay"] += float(row.get("现金支付", "0") or 0)

            month_key = date_str[:7]
            monthly_revenue[month_key] += revenue

        except (ValueError, KeyError) as e:
            errors.append(f"第 {total_rows} 行: {e}")
            continue

    if not members and anonymous["records"] == 0:
        return {"error": "清洗后无有效数据", "total_rows": total_rows}

    # 全佚名 → 跳过 RFM 计算，直接返回匿名汇总
    if not members:
        return {
            "summary": {
                "total_members": 0,
                "total_revenue": round(anonymous["revenue"], 0),
                "anonymous_records": anonymous["records"],
                "anonymous_revenue": round(anonymous["revenue"], 0),
            },
            "segments": [], "lifecycle": {}, "cohorts": [], "monthly": [],
            "total_rows": total_rows, "errors": [],
        }

    # ── 第三步：排序 ──
    all_rows.sort(key=lambda r: r.get("日期", ""))

    # ── 第四步：计算每个会员的 RFM ──
    today = date.today()
    rfm_list = []
    for uid, m in members.items():
        last_date = max(m["dates"])
        r = (today - last_date).days
        f = m["transactions"]
        mon = m["total_revenue"]
        rfm_list.append({
            "id": uid,
            "name": m["name"],
            "phone": m["phone"],
            "r": r,
            "f": f,
            "m": mon,
            "first_date": m["first_date"].strftime("%Y-%m-%d") if m["first_date"] else "",
            "last_date": last_date.strftime("%Y-%m-%d"),
            "total_revenue": mon,
            "avg_per_visit": round(mon / f, 0) if f > 0 else 0,
            "card_pay": m["card_pay"],
            "stored_card_pay": m["stored_card_pay"],
            "cash_pay": m["cash_pay"],
        })

    n = len(rfm_list)
    avg_r = sum(x["r"] for x in rfm_list) / n
    avg_f = sum(x["f"] for x in rfm_list) / n
    avg_m = sum(x["m"] for x in rfm_list) / n

    # ── RFM 8 类分群 ──
    segments_data = {name: [] for name in SEGMENT_NAMES}
    for member in rfm_list:
        seg = _classify_rfm(member["r"], member["f"], member["m"], avg_r, avg_f, avg_m)
        segments_data[seg].append(member)

    # ── 生命周期阶段 ──
    lifecycle_stages = defaultdict(list)
    for member in rfm_list:
        stage = _classify_lifecycle(member["r"], member["f"], member["m"], avg_m)
        lifecycle_stages[stage].append(member)

    # ── CLV 估算 ──
    total_clv = 0.0
    for member in rfm_list:
        member["clv"] = _calc_clv(member, avg_f)
        total_clv += member["clv"]
    avg_clv = round(total_clv / n, 0) if n > 0 else 0

    # ── 同批次留存曲线 ──
    cohorts = defaultdict(lambda: {"total": 0, "retained": defaultdict(int)})
    for member in rfm_list:
        if member["first_date"]:
            cohort_month = member["first_date"][:7]  # "2025-06"
            cohorts[cohort_month]["total"] += 1
            # 算一下从首月到现在过了几个月，每个月是否还有消费
            first = datetime.strptime(member["first_date"], "%Y-%m-%d").date()
            for d in members[member["id"]]["dates"]:
                month_diff = (d.year - first.year) * 12 + (d.month - first.month)
                if 0 <= month_diff <= 24:
                    cohorts[cohort_month]["retained"][month_diff] += 1

    # ── 构建结果 ──
    seg_results = []
    total_revenue = sum(x["m"] for x in rfm_list) + anonymous["revenue"]
    for seg_name in SEGMENT_NAMES:
        members_list = segments_data[seg_name]
        if not members_list:
            continue
        seg_revenue = sum(x["m"] for x in members_list)
        seg_results.append({
            "name": seg_name,
            "members": len(members_list),
            "color": SEGMENT_COLORS.get(seg_name, "#ccc"),
            "revenue_yuan": round(seg_revenue, 0),
            "avg_per_visit": round(seg_revenue / len(members_list), 0),
            "pct_of_total": round(len(members_list) / n * 100, 1),
            "revenue_pct": round(seg_revenue / total_revenue * 100, 1),
            "r_label": "近" if members_list[0]["r"] < avg_r else "远",
            "f_label": "高" if members_list[0]["f"] >= avg_f else "低",
            "m_label": "高" if members_list[0]["m"] >= avg_m else "低",
        })

    lifecycle_result = {}
    for stage in ["新客期", "成长期", "成熟期", "休眠期", "流失期", "稳定期"]:
        members_list = lifecycle_stages.get(stage, [])
        if members_list:
            lifecycle_result[stage] = {
                "count": len(members_list),
                "pct": round(len(members_list) / n * 100, 1),
                "avg_revenue": round(sum(x["m"] for x in members_list) / len(members_list), 0),
            }

    cohort_result = []
    for month in sorted(cohorts.keys()):
        c = cohorts[month]
        row = {"month": month, "total": c["total"]}
        for m_offset in range(0, 13):
            retained = c["retained"].get(m_offset, 0)
            row[f"m{m_offset}"] = retained
            row[f"m{m_offset}_pct"] = round(retained / c["total"] * 100, 1) if c["total"] > 0 else 0
        cohort_result.append(row)

    monthly = [{"month": k, "total": round(v, 0)} for k, v in sorted(monthly_revenue.items())]

    return {
        "summary": {
            "total_members": n,
            "total_revenue": round(total_revenue, 0),
            "total_transactions": sum(x["f"] for x in rfm_list),
            "avg_r_days": round(avg_r, 0),
            "avg_f_times": round(avg_f, 1),
            "avg_m_yuan": round(avg_m, 0),
            "avg_clv_yuan": avg_clv,
            "anonymous_records": anonymous["records"],
            "anonymous_revenue": round(anonymous["revenue"], 0),
            "date_range": f"{min(monthly_revenue.keys())} ~ {max(monthly_revenue.keys())}" if monthly_revenue else "",
        },
        "segments": seg_results,
        "lifecycle": lifecycle_result,
        "cohorts": cohort_result,
        "monthly": monthly,
        "total_rows": total_rows,
        "errors": errors[:10],
    }


def analyze_from_db(days: int = 0) -> dict:
    """从数据库读取分析。days=0 表示查全部数据。"""
    """从数据库读取数据后跑 RFM 分析。跟 analyze() 返回相同格式。

    用于 RFM 2.0——数据已入库，不依赖上传文件。
    """
    from database import query_members

    members_list = query_members(days=days)
    if not members_list:
        return {"error": f"数据库中暂无最近 {days} 天的数据，请先上传 CSV 导入"}

    # 把数据库结果转成跟 CSV 模式一样的 rfm_list 结构
    rfm_list = []
    for m in members_list:
        r = m["r_days"]
        f = m["visit_count"]
        revenue = m["total_revenue"]
        rfm_list.append({
            "name": m["member_name"],
            "phone": m["phone"],
            "r": r,
            "f": f,
            "m": revenue,
            "last_date": m["last_date"],
            "first_date": m["first_date"],
            "avg_per_visit": m["avg_per_visit"],
        })

    n = len(rfm_list)
    avg_r = sum(x["r"] for x in rfm_list) / n
    avg_f = sum(x["f"] for x in rfm_list) / n
    avg_m = sum(x["m"] for x in rfm_list) / n
    total_revenue = sum(x["m"] for x in rfm_list)

    # ── RFM 8 类分群 ──
    segments_data = {name: [] for name in SEGMENT_NAMES}
    for member in rfm_list:
        seg = _classify_rfm(member["r"], member["f"], member["m"], avg_r, avg_f, avg_m)
        segments_data[seg].append(member)

    # ── 生命周期 ──
    lifecycle_stages = defaultdict(list)
    for member in rfm_list:
        stage = _classify_lifecycle(member["r"], member["f"], member["m"], avg_m)
        lifecycle_stages[stage].append(member)

    # ── CLV ──
    total_clv = 0.0
    for member in rfm_list:
        member["clv"] = _calc_clv(member, avg_f)
        total_clv += member["clv"]
    avg_clv = round(total_clv / n, 0) if n > 0 else 0

    # ── 构建结果（跟 analyze() 相同格式）──
    seg_results = []
    for seg_name in SEGMENT_NAMES:
        mlist = segments_data[seg_name]
        if not mlist:
            continue
        seg_revenue = sum(x["m"] for x in mlist)
        seg_results.append({
            "name": seg_name,
            "members": len(mlist),
            "color": SEGMENT_COLORS.get(seg_name, "#ccc"),
            "revenue_yuan": round(seg_revenue, 0),
            "avg_per_visit": round(seg_revenue / len(mlist), 0),
            "pct_of_total": round(len(mlist) / n * 100, 1),
            "revenue_pct": round(seg_revenue / total_revenue * 100, 1),
            "r_label": "近" if mlist[0]["r"] < avg_r else "远",
            "f_label": "高" if mlist[0]["f"] >= avg_f else "低",
            "m_label": "高" if mlist[0]["m"] >= avg_m else "低",
        })

    lifecycle_result = {}
    for stage in ["新客期", "成长期", "成熟期", "休眠期", "流失期", "稳定期"]:
        mlist = lifecycle_stages.get(stage, [])
        if mlist:
            lifecycle_result[stage] = {
                "count": len(mlist),
                "pct": round(len(mlist) / n * 100, 1),
                "avg_revenue": round(sum(x["m"] for x in mlist) / len(mlist), 0),
            }

    from database import get_date_range, _connect
    start, end = get_date_range()

    # 月度营收趋势（全部数据，不受 days 限制）
    monthly_revenue = {}
    with _connect() as conn:
        rows = conn.execute(
            "SELECT SUBSTR(trans_date,1,7) as month, SUM(revenue) as total "
            "FROM transactions GROUP BY month ORDER BY month"
        ).fetchall()
        for r in rows:
            monthly_revenue[r["month"]] = r["total"]
    monthly = [{"month": k, "total": round(v, 0)} for k, v in sorted(monthly_revenue.items())]

    return {
        "summary": {
            "total_members": n,
            "total_revenue": round(total_revenue, 0),
            "total_transactions": sum(x["f"] for x in rfm_list),
            "avg_r_days": round(avg_r, 0),
            "avg_f_times": round(avg_f, 1),
            "avg_m_yuan": round(avg_m, 0),
            "avg_clv_yuan": avg_clv,
            "anonymous_records": 0,
            "anonymous_revenue": 0,
            "date_range": f"{start} ~ {end}" if start else "",
        },
        "segments": seg_results,
        "lifecycle": lifecycle_result,
        "cohorts": [],
        "monthly": monthly,
        "total_rows": sum(x["f"] for x in rfm_list),
        "errors": [],
    }
