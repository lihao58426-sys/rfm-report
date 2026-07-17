"""
RFM 分析报告 — FastAPI 服务器
=============================
用法：python server.py → 浏览器打开 http://localhost:8001
"""

import base64
import html
import logging
import os
import secrets
from pathlib import Path

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader

from analysis import analyze, analyze_from_db
from database import import_csv, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

from fastapi.staticfiles import StaticFiles

app = FastAPI(title="会员价值诊断报告")

# ── 鉴权 ──
# 会员手机号数据涉及隐私，上云前必须设 RFM_PASSWORD。
# 本地不设时跳过鉴权，跟以前一样用。
RFM_PASSWORD = os.getenv("RFM_PASSWORD", "")

def _check_auth(request: Request) -> bool:
    if not RFM_PASSWORD:
        return True
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(auth[6:]).decode("utf-8")
        _, password = decoded.split(":", 1)
        return secrets.compare_digest(password, RFM_PASSWORD)
    except Exception:
        return False

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    from fastapi.responses import JSONResponse
    if not _check_auth(request):
        return JSONResponse({"detail": "请输入密码"}, status_code=401,
                          headers={"WWW-Authenticate": 'Basic realm="RFM Report"'})
    return await call_next(request)

# ECharts 等静态文件
app.mount("/static", StaticFiles(directory="static"), name="static")

# 绕过 Jinja2Templates 的缓存 bug，直接用 Jinja2 加载模板
jinja_env = Environment(loader=FileSystemLoader("templates"))

def render_template(name: str, **kwargs) -> str:
    """手动加载 + 渲染 Jinja2 模板，返回 HTML 字符串"""
    template = jinja_env.get_template(name)
    return template.render(**kwargs)


@app.get("/", response_class=HTMLResponse)
async def upload_page(request: Request):
    return render_template("upload.html", request=request)


@app.post("/report", response_class=HTMLResponse)
async def show_report(request: Request, files: list[UploadFile] = File(...)):
    if not files:
        return HTMLResponse("<h2>请选择 CSV 文件</h2>")

    logger.info(f"收到 {len(files)} 个文件")
    result = analyze(files)

    if "error" in result:
        return HTMLResponse(f"<h2>分析失败</h2><pre>{html.escape(result['error'])}</pre>")

    return render_template("report.html", request=request, result=result)


@app.post("/import", response_class=HTMLResponse)
async def import_and_report(request: Request, files: list[UploadFile] = File(...)):
    """上传 CSV → 入库 → 从数据库取数据生成 RFM 报告"""
    if not files:
        return HTMLResponse("<h2>请选择 CSV 文件</h2>")

    init_db()
    total = 0
    for f in files:
        content = f.file.read()
        if isinstance(content, bytes):
            content = content.decode("utf-8-sig")
        try:
            total += import_csv(content)
        except ValueError as e:
            return HTMLResponse(f"<h2>导入失败</h2><pre>{html.escape(str(e))}</pre>")

    logger.info(f"导入完成: {total} 条")

    result = analyze_from_db(days=0)  # 查全部数据
    if "error" in result:
        return HTMLResponse(f"<h2>{html.escape(result['error'])}</h2>")

    return render_template("report.html", request=request, result=result,
                         imported=total)


@app.get("/query", response_class=HTMLResponse)
async def query_page(request: Request):
    """会员数据查询页——按关键词/分类/时间筛选"""
    from database import query_members

    keyword = request.query_params.get("keyword", "")
    segment = request.query_params.get("segment", "")
    days = int(request.query_params.get("days", "90"))

    members = query_members(days=days, keyword=keyword or None,
                          segment=segment or None)

    return render_template("query.html", request=request,
                         members=members, keyword=keyword,
                         segment=segment, days=days)


@app.get("/query/export")
async def export_query(request: Request):
    """导出当前查询结果为 CSV"""
    from database import query_members
    import io

    keyword = request.query_params.get("keyword", "")
    segment = request.query_params.get("segment", "")
    days = int(request.query_params.get("days", "90"))

    members = query_members(days=days, keyword=keyword or None,
                          segment=segment or None)

    output = io.StringIO()
    output.write("会员姓名,手机号,消费次数,累计消费(元),客单价(元),首次来访,最近来访,RFM分类\n")
    for m in members:
        output.write(f'{m["member_name"]},{m["phone"]},{m["visit_count"]},'
                    f'{m["total_revenue"]},{m["avg_per_visit"]},'
                    f'{m["first_date"]},{m["last_date"]},{m["segment"]}\n')

    from fastapi.responses import Response
    return Response(
        content=output.getvalue().encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=rfm_query_export.csv"},
    )


if __name__ == "__main__":
    import uvicorn
    logger.info("启动服务器: http://localhost:8001")
    uvicorn.run(app, host="0.0.0.0", port=8001)
