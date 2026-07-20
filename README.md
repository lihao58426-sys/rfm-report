# RFM 客户价值分析报告

某收银系统会员消费 CSV → RFM 8 类分群 + 数据分析 + 会员明细查询 + CSV 导出。

> 数据存储在 SQLite，永久保存。每次分析基于所选时间窗口动态计算——同一会员在不同时间段分类可能不同。

## 快速开始

```bash
pip install -r requirements.txt
python server.py
# 浏览器打开 http://localhost:8001
```

## 功能

- 上传某收银系统 CSV（支持多文件合并，自动去重表头）
- 数据清洗：过滤退款、日期兼容、中英文括号解析、佚名单独统计
- **RFM 分析** — 按手机号分组 → R/F/M 打分 → 8 类分群（动态计算，不存库）
- **会员查询页** — 选时间范围（动态重算 RFM） + 分类筛选 + 关键词搜索 → 导出 CSV
- **数据管理首页** — 批次列表 + 多选删除 + 侧边上传
- **月度营收趋势** — 全量数据自动汇总
- pytest 测试（38 用例）

## Docker 部署

```bash
docker compose up -d --build
# 打开 http://localhost:8001
```

## 安全

- HTTP Basic Auth（RFM_PASSWORD 环境变量控制）
- XSS 防护（html.escape）
- 会员手机号数据保护

## 在线 Demo

https://你的域名:8001（备案后开放）

## 技术栈

Python · FastAPI · SQLite · PyTest · Docker · Jinja2 · ECharts

## 项目结构

```
rfm_report/
├── server.py              # FastAPI（5 个路由）
├── analysis.py            # RFM 引擎 + 数据库驱动分析
├── database.py            # SQLite · CSV 导入清洗 · 批次管理 · 会员聚合查询
├── templates/             # home(数据管理) / report(分析报告) / query(会员查询)
├── static/                # echarts.min.js
├── tests/                 # 38 用例全绿
├── docker-compose.yml     # 含 DB 卷挂载
└── Dockerfile
```

## 版本

V2.0 — 数据库持久化 + 数据管理首页 + 动态查询 + 分类筛选 + CSV 导出

## License

MIT
