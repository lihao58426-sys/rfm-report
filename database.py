"""
RFM 数据存储 — 上传 CSV → 清洗入库 → 长期保存
==============================================
银豹每 3 个月导一次会员消费明细，存在一张表里。
同一会员多条记录，查询时按会员聚合展示。

表: transactions
  会员姓名 | 手机号 | 消费日期 | 消费金额 | 上传批次

用法:
  from database import import_csv, query_members
  count = import_csv(csv_content)          # 导入，自动去重
  members = query_members(days=90)         # 查最近90天的会员汇总
"""

import csv
import io
import logging
import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)

DB_PATH = "rfm_data.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """建表（表不存在就创建）"""
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                member_name TEXT    NOT NULL DEFAULT '',
                phone       TEXT    NOT NULL DEFAULT '',
                trans_date  TEXT    NOT NULL,
                revenue     REAL    NOT NULL DEFAULT 0,
                batch       TEXT    NOT NULL DEFAULT '',
                created_at  TEXT    DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(phone, trans_date, revenue)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_phone ON transactions(phone)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_date ON transactions(trans_date)
        """)
        conn.commit()
    logger.info("数据库就绪")


def import_csv(csv_content: str) -> int:
    """
    导入银豹导出的 CSV，自动清洗 + 去重。
    返回本次导入的新记录数。
    """
    init_db()
    reader = csv.DictReader(io.StringIO(csv_content))

    # 验证表头
    headers = reader.fieldnames or []
    required = ["会员", "日期", "实收金额"]
    missing = [c for c in required if c not in headers]
    if missing:
        raise ValueError(f"缺少必要列: {', '.join(missing)}。表头: {headers}")

    batch = datetime.now().strftime("%Y%m%d-%H%M")
    count = 0

    with _connect() as conn:
        for row in reader:
            # 清洗
            member_raw = row.get("会员", "").strip()
            date_str = row.get("日期", "").strip()
            # 跳过退款/退货
            txn_type = row.get("类型", "").strip()
            if "退款" in txn_type or "退货" in txn_type:
                continue
            if not date_str:
                continue
            # 日期格式：兼容 YYYY-MM-DD 和 YYYY/MM/DD，带时间也行
            date_str_clean = date_str[:10].replace("/", "-")
            try:
                datetime.strptime(date_str_clean, "%Y-%m-%d")
            except ValueError:
                continue

            revenue_str = row.get("实收金额", "0").strip()
            try:
                revenue = float(revenue_str)
            except ValueError:
                revenue = 0.0
            if revenue <= 0:
                continue

            # 解析会员: "张三（13800138000）" → 张三, 13800138000
            # 佚名/无会员信息 → 跳过（不参与 RFM 分析）
            if not member_raw or member_raw == "-":
                continue

            import re
            # 兼容中文括号（）和英文括号()
            match = re.search(r"[（(](\d{5,20})[）)]", member_raw)
            if match:
                phone = match.group(1)
                name = member_raw[:match.start()].strip()
            else:
                phone = member_raw  # 没有手机号时用会员名本身作为唯一标识
                name = member_raw

            # 插入，重复跳过
            try:
                conn.execute(
                    "INSERT INTO transactions (member_name, phone, trans_date, revenue, batch) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (name, phone, date_str, revenue, batch),
                )
                count += 1
            except sqlite3.IntegrityError:
                pass  # 已存在，跳过

        conn.commit()

    logger.info(f"导入完成: {count} 条新增记录（批次 {batch}）")
    return count


def _classify_member(r: int, f: int, m: float, avg_r: float, avg_f: float, avg_m: float) -> str:
    """给单个会员打 RFM 分类标签"""
    r_label = "近" if r < avg_r else "远"
    f_label = "高" if f >= avg_f else "低"
    m_label = "高" if m >= avg_m else "低"
    if r_label == "近" and f_label == "高" and m_label == "高": return "重要价值客户"
    if r_label == "远" and f_label == "高" and m_label == "高": return "重要唤回客户"
    if r_label == "近" and f_label == "低" and m_label == "高": return "重要发展客户"
    if r_label == "远" and f_label == "低" and m_label == "高": return "重要挽留客户"
    if r_label == "近" and f_label == "高" and m_label == "低": return "一般活跃客户"
    if r_label == "远" and f_label == "高" and m_label == "低": return "一般客户"
    if r_label == "近" and f_label == "低" and m_label == "低": return "新客/低频客户"
    return "流失客户"


def query_members(days: int = 90, segment: str | None = None,
                  keyword: str | None = None) -> list[dict]:
    """
    查询会员汇总——按会员聚合原始交易，并动态计算 RFM 分类标签。

    Args:
        days: 查最近几天，默认 90
        segment: 可选，只查某个 RFM 分类的会员
        keyword: 可选，搜索会员名/手机号

    Returns:
        每个会员一行，含：姓名、手机、消费次数、累计金额、首次/最近日期、客单价、距今天数、RFM分类
    """
    init_db()
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    sql = """
        SELECT member_name, phone,
               COUNT(*) as visit_count,
               SUM(revenue) as total_revenue,
               MIN(trans_date) as first_date,
               MAX(trans_date) as last_date,
               ROUND(SUM(revenue) / COUNT(*), 0) as avg_per_visit,
               CAST(julianday('now') - julianday(MAX(trans_date)) AS INTEGER) as r_days
        FROM transactions
        WHERE trans_date >= ?
    """
    params: list = [cutoff]

    if keyword:
        sql += " AND (member_name LIKE ? OR phone LIKE ?)"
        kw = f"%{keyword}%"
        params.extend([kw, kw])

    sql += " GROUP BY CASE WHEN phone = '' THEN 'NONAME_' || member_name ELSE phone END ORDER BY total_revenue DESC"

    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()

    members = [dict(r) for r in rows]
    if not members:
        return []

    # 计算平均 R/F/M，给每个会员打分类标签
    n = len(members)
    avg_r = sum(m["r_days"] for m in members) / n
    avg_f = sum(m["visit_count"] for m in members) / n
    avg_m = sum(m["total_revenue"] for m in members) / n

    for m in members:
        m["segment"] = _classify_member(
            m["r_days"], m["visit_count"], m["total_revenue"], avg_r, avg_f, avg_m)

    # 按分类筛选
    if segment:
        members = [m for m in members if m["segment"] == segment]

    return members


def get_date_range() -> tuple[str, str]:
    """返回数据库中最早和最晚的日期"""
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT MIN(trans_date) as min_d, MAX(trans_date) as max_d FROM transactions"
        ).fetchone()
    if row and row["min_d"]:
        return row["min_d"], row["max_d"]
    return "", ""
