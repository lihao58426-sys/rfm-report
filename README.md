# RFM 客户价值分析报告

纯手写 Vanilla JS + CSS 的 RFM 客户价值分析系统。支持上传银豹 CSV → 自动 RFM 分析 → 8 类分群 → 生命周期 → CLV 估算 → 留存曲线 → 浏览器查看完整报告。

## 两种模式

| 模式 | 入口 | 用途 |
|------|------|------|
| 静态报告 | `index.html` | 脱敏样例展示（数据写死在 config.js） |
| 在线分析 | `python server.py` | 上传真实 CSV → 自动出报告（FastAPI 后端） |

## 功能

### 静态版（index.html）
- RFM 8 类客户分群 + 可视化
- 月度淡旺季堆叠柱状图
- 行动优先级矩阵（P0-P3）+ ROI 估算
- 响应式设计（PC + 手机）

### 在线分析版（python server.py）
- 上传银豹 CSV（支持多文件合并，自动去重表头）
- 数据清洗：过滤退款/空会员/异常金额，佚名客户单独汇总
- **RFM 分析** — 按手机号分组 → R/F/M 打分 → 8 类分群
- **客户生命周期** — 新客→成长→成熟→休眠→流失，每阶段策略建议
- **CLV 估算** — 客户终身价值，知道一个新客值多少钱
- **留存曲线** — 同批次新客每月留存率，区分"真客户"和"凑热闹"
- **月度营收趋势** — 12+ 个月自动汇总

## 技术栈

### 前端
Vanilla JS · CSS · HTML5 · Jinja2 模板

### 后端
Python · FastAPI · RFM 分析模型 · CSV 解析

## 使用

```bash
# 在线分析模式
pip install fastapi uvicorn python-multipart jinja2
python server.py
# 浏览器打开 http://localhost:8000 → 上传 CSV → 看报告
```

## 项目结构

```
rfm_report/
├── index.html           # 静态报告（脱敏样例）
├── style.css / rfm.js / charts.js / config.js  # 静态版前端
├── analysis.py          # RFM + 生命周期 + CLV + 留存曲线 引擎
├── server.py            # FastAPI 服务器
├── templates/
│   ├── upload.html      # 上传页面
│   └── report.html      # 在线报告模板
└── pyproject.toml
```

## 设计理念

不只是展示数据——展示商业分析能力和可落地的运营建议。每张图对应一个老板要做的决策。
