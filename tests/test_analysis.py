"""
测试 analysis.py — 会员解析 + RFM 分类 + 生命周期判断
"""

import sys
sys.path.insert(0, '..')

import csv
import io
from analysis import _parse_member, _classify_rfm, _classify_lifecycle, analyze


class TestParseMember:
    """测试会员字段解析"""

    def test_normal_member(self):
        name, phone = _parse_member("张三（13800138000）")
        assert name == "张三"
        assert phone == "13800138000"

    def test_anonymous(self):
        name, phone = _parse_member("-")
        assert name == "佚名"
        assert phone == ""

    def test_empty(self):
        name, phone = _parse_member("")
        assert name == "佚名"
        assert phone == ""

    def test_no_phone(self):
        """没有手机号 → 名字当 ID"""
        name, phone = _parse_member("李四")
        assert name == "李四"
        assert phone == "李四"  # 没手机号用名字


class TestClassifyRfm:
    """测试 RFM 8 类分群"""

    def test_important_value(self):
        """近 + 高 + 高 → 重要价值客户"""
        result = _classify_rfm(r=10, f=8, m=5000, avg_r=30, avg_f=3, avg_m=1000)
        assert result == "重要价值客户"

    def test_important_recall(self):
        """远 + 高 + 高 → 重要唤回客户"""
        result = _classify_rfm(r=60, f=8, m=5000, avg_r=30, avg_f=3, avg_m=1000)
        assert result == "重要唤回客户"

    def test_lost_customer(self):
        """远 + 低 + 低 → 流失客户"""
        result = _classify_rfm(r=100, f=1, m=50, avg_r=30, avg_f=3, avg_m=1000)
        assert result == "流失客户"

    def test_new_customer(self):
        """近 + 低 + 低 → 新客/低频客户"""
        result = _classify_rfm(r=5, f=1, m=50, avg_r=30, avg_f=3, avg_m=1000)
        assert result == "新客/低频客户"

    def test_all_8_categories_exist(self):
        """8 种分类都能被命中"""
        categories = set()
        scenarios = [
            (10, 8, 5000, 30, 3, 1000),   # 近高高 = 重要价值
            (60, 8, 5000, 30, 3, 1000),   # 远高高 = 重要唤回
            (10, 1, 5000, 30, 3, 1000),   # 近低高 = 重要发展
            (60, 1, 5000, 30, 3, 1000),   # 远低高 = 重要挽留
            (10, 8, 50, 30, 3, 1000),     # 近高低 = 一般活跃
            (60, 8, 50, 30, 3, 1000),     # 远高低 = 一般客户
            (10, 1, 50, 30, 3, 1000),     # 近低低 = 新客/低频
            (60, 1, 50, 30, 3, 1000),     # 远低低 = 流失
        ]
        for args in scenarios:
            categories.add(_classify_rfm(*args))
        assert len(categories) == 8


class TestClassifyLifecycle:
    """测试生命周期阶段判断"""

    def test_new_customer(self):
        assert _classify_lifecycle(r=5, f=1, m=50, avg_m=500) == "新客期"

    def test_growing(self):
        assert _classify_lifecycle(r=10, f=4, m=300, avg_m=500) == "成长期"

    def test_mature(self):
        assert _classify_lifecycle(r=10, f=10, m=2000, avg_m=500) == "成熟期"

    def test_dormant(self):
        assert _classify_lifecycle(r=60, f=10, m=2000, avg_m=500) == "休眠期"

    def test_lost(self):
        assert _classify_lifecycle(r=200, f=1, m=50, avg_m=500) == "流失期"


class TestAnalyze:
    """测试主分析函数"""

    def _make_csv(self, rows: str) -> list:
        """把字符串转成模拟的上传文件列表"""
        return [io.BytesIO(rows.encode('utf-8-sig'))]

    def test_analyze_basic(self):
        """最基本的 CSV → 能跑通"""
        csv_content = (
            "流水号,日期,类型,会员,实收金额,次卡支付,储值卡支付,储值本金支付,储值赠送支付,现金支付\n"
            "001,2026-07-01 10:00,销售,张三（13800138000）,100,0,0,0,0,100\n"
            "002,2026-07-02 10:00,销售,张三（13800138000）,200,0,0,0,0,200\n"
            "003,2026-07-01 11:00,销售,李四（13900139000）,300,0,0,0,0,300\n"
        )
        files = self._make_csv(csv_content)
        result = analyze(files)

        assert "error" not in result
        assert result["summary"]["total_members"] >= 2
        assert result["summary"]["total_revenue"] >= 600
        assert len(result["segments"]) >= 1
        assert len(result["monthly"]) >= 1

    def test_analyze_skips_refund(self):
        """退款行 → 被跳过"""
        csv_content = (
            "流水号,日期,类型,会员,实收金额,次卡支付,储值卡支付,储值本金支付,储值赠送支付,现金支付\n"
            "001,2026-07-01 10:00,销售,张三（13800138000）,100,0,0,0,0,100\n"
            "002,2026-07-01 11:00,退款,张三（13800138000）,50,0,0,0,0,50\n"
        )
        files = self._make_csv(csv_content)
        result = analyze(files)
        # 退款被跳过，只算销售
        assert result["summary"]["total_revenue"] == 100.0

    def test_analyze_anonymous_handling(self):
        """佚名 → 单独汇总，不参与 RFM 分组"""
        csv_content = (
            "流水号,日期,类型,会员,实收金额,次卡支付,储值卡支付,储值本金支付,储值赠送支付,现金支付\n"
            "001,2026-07-01 10:00,销售,-,100,0,0,0,0,100\n"
            "002,2026-07-01 11:00,销售,-,200,0,0,0,0,200\n"
        )
        files = self._make_csv(csv_content)
        result = analyze(files)
        # 佚名记录被单独统计
        assert result["summary"]["anonymous_records"] >= 1
        assert result["summary"]["anonymous_revenue"] >= 300
        # 但会员数为 0
        assert result["summary"]["total_members"] == 0

    def test_analyze_empty_csv(self):
        """空 CSV → 返回错误不崩溃"""
        csv_content = "流水号,日期,类型,会员,实收金额\n"
        files = self._make_csv(csv_content)
        result = analyze(files)
        assert "error" in result

    def test_analyze_missing_columns(self):
        """缺少必要列 → 返回错误"""
        csv_content = "流水号,日期\n001,2026-07-01\n"
        files = self._make_csv(csv_content)
        result = analyze(files)
        assert "error" in result
