"""
RFM 分类会员导出 — 分析完成后生成 8 份 CSV，每份一个客户群
========================================================
用法：
  from export_csv import export_segments
  export_segments(result, "output/")   # result 来自 analysis.analyze()

每份 CSV 包含：会员姓名、手机号、消费金额、消费次数、最近消费日期
"""

import csv
import os
from datetime import datetime


def export_segments(result: dict, output_dir: str = ".") -> list[str]:
    """
    从分析结果导出分类 CSV。每个 RFM 分群一个文件。

    Returns:
        生成的文件路径列表
    """
    segments = result.get("segments", [])
    if not segments:
        return []

    os.makedirs(output_dir, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    files = []

    for seg in segments:
        members = seg.get("members_detail", [])
        if not members:
            continue

        # 文件名：RFM-重要价值客户-20260717.csv
        filename = f"RFM-{seg['name']}-{today}.csv"
        filepath = os.path.join(output_dir, filename)

        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["会员姓名", "手机号", "消费金额(元)", "消费次数",
                            "最近消费日期", "客单价(元)", "RFM标签"])
            for m in members:
                r_label = "近" if m["r"] <= 30 else "中" if m["r"] <= 90 else "远"
                writer.writerow([
                    m.get("name", ""),
                    m.get("phone", ""),
                    round(m.get("m", 0), 0),
                    m.get("f", 0),
                    m.get("last_date", ""),
                    round(m.get("avg_per_visit", 0), 0),
                    f"R{r_label}/F{m.get('f',0)}/M{round(m.get('m',0),0)}",
                ])

        files.append(filepath)

    # 汇总文件：所有会员一起导出（供老板直接用）
    summary_path = os.path.join(output_dir, f"RFM-全量会员汇总-{today}.csv")
    with open(summary_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["会员姓名", "手机号", "消费金额(元)", "消费次数",
                        "最近消费日期", "所属分群"])
        for seg in segments:
            for m in seg.get("members_detail", []):
                writer.writerow([
                    m.get("name", ""),
                    m.get("phone", ""),
                    round(m.get("m", 0), 0),
                    m.get("f", 0),
                    m.get("last_date", ""),
                    seg["name"],
                ])
    files.append(summary_path)

    return files
