"""database.py 功能测试"""
import io
import os
import pytest
from database import init_db, import_csv, query_members, list_batches, delete_batch, get_date_range, _connect
import database as db_module

TEST_CSV = "会员,日期,实收金额\n张三（13801）,2026-07-01,100\n张三（13801）,2026-07-10,200\n李四（13902）,2026-07-15,500\n"


@pytest.fixture(autouse=True)
def clean_db(tmp_path, monkeypatch):
    """每个测试用独立数据库，避免 Windows 文件锁"""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    yield
    # 测试完走，tmp_path 自动清理


class TestInitDb:
    def test_table_created(self):
        """表创建成功"""
        with _connect() as conn:
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        assert "transactions" in tables

    def test_idempotent(self):
        """重复建表不报错"""
        init_db()
        init_db()


class TestImportCsv:
    def test_basic_import(self):
        """正常导入并计数"""
        count = import_csv(TEST_CSV)
        assert count == 3

    def test_import_preserves_data(self):
        """导入后数据库有正确数据"""
        import_csv(TEST_CSV)
        with _connect() as conn:
            row = conn.execute("SELECT * FROM transactions WHERE phone='13801' LIMIT 1").fetchone()
        assert row["member_name"] == "张三"
        assert row["revenue"] == 100.0

    def test_duplicate_import_is_allowed(self):
        """重复导入同一条也不拦——同会员同日同金额可能是两笔不同交易"""
        import_csv(TEST_CSV)
        count2 = import_csv(TEST_CSV)
        assert count2 == 3  # 不做去重

    def test_invalid_columns(self):
        """缺必要列时报错"""
        with pytest.raises(ValueError, match="缺少必要列"):
            import_csv("姓名,日期,金额\n张三,2026-07-01,100")

    def test_skip_refund(self):
        """退款记录跳过"""
        csv = "会员,日期,实收金额,类型\n张三（13801）,2026-07-01,100,退款"
        count = import_csv(csv)
        assert count == 0

    def test_negative_revenue_kept(self):
        """负数也入库——数据清洗不拦截负收入（银豹可能记折让）"""
        csv = "会员,日期,实收金额\n张三（13801）,2026-07-01,-50"
        count = import_csv(csv)
        assert count == 1

    def test_zero_revenue_kept(self):
        """金额为0保留（礼品包）"""
        csv = "会员,日期,实收金额\n张三（13801）,2026-07-01,0"
        count = import_csv(csv)
        assert count == 1

    def test_anonymous_stored(self):
        """佚名记录入库为佚名"""
        csv = "会员,日期,实收金额\n-,2026-07-01,100"
        count = import_csv(csv)
        assert count == 1
        with _connect() as conn:
            row = conn.execute("SELECT * FROM transactions WHERE member_name='佚名'").fetchone()
        assert row is not None

    def test_english_brackets(self):
        """英文括号解析手机号"""
        csv = "会员,日期,实收金额\n张三(13800000001),2026-07-01,100"
        count = import_csv(csv)
        assert count == 1
        with _connect() as conn:
            row = conn.execute("SELECT phone FROM transactions").fetchone()
        assert row["phone"] == "13800000001"


class TestQueryMembers:
    def test_default_all_data(self):
        """days=0 查全库"""
        import_csv(TEST_CSV)
        members = query_members(days=0)
        assert len(members) == 2  # 张三, 李四

    def test_days_filter(self):
        """days=30 过滤旧数据"""
        csv = "会员,日期,实收金额\n老客户（13901）,2025-01-01,50\n新客户（13902）,2026-07-01,50"
        import_csv(csv)
        members = query_members(days=30)
        assert len(members) == 1  # 只有新客户

    def test_keyword_search(self):
        """按姓名搜索"""
        import_csv(TEST_CSV)
        members = query_members(keyword="张三")
        assert len(members) == 1
        assert members[0]["member_name"] == "张三"

    def test_segment_filter(self):
        """按分类筛选"""
        import_csv(TEST_CSV)
        members = query_members(days=0)
        # 所有会员都有分类标签
        segments = {m["segment"] for m in members}
        assert len(segments) > 0

    def test_anonymous_in_db(self):
        """佚名记录入库并可以查到——analyze_from_db 负责过滤"""
        csv = "会员,日期,实收金额\n张三（13801）,2026-07-01,100\n-,2026-07-01,50"
        import_csv(csv)
        members = query_members(days=0, segment=None)
        phones = [m["phone"] for m in members]
        assert "佚名" in phones  # 佚名也入库了，analyze_from_db 才做过滤


class TestBatchManagement:
    def test_list_batches(self):
        """list_batches 返回正确"""
        import_csv(TEST_CSV)
        batches = list_batches()
        assert len(batches) == 1
        assert batches[0]["records"] == 3

    def test_delete_batch(self):
        """delete_batch 删除指定批次"""
        import_csv(TEST_CSV)
        batches = list_batches()
        deleted = delete_batch(batches[0]["batch"])
        assert deleted == 3
        # 删完为空
        with _connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        assert count == 0

    def test_get_date_range(self):
        """get_date_range 返回最早最晚"""
        import_csv(TEST_CSV)
        start, end = get_date_range()
        assert start == "2026-07-01"
        assert end == "2026-07-15"
