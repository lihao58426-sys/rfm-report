"""
RFM 分析报告 — FastAPI 服务器
=============================
用法：python server.py → 浏览器打开 http://localhost:8000
"""

import logging
from pathlib import Path

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader

from analysis import analyze

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="会员价值诊断报告")

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
        return HTMLResponse(f"<h2>分析失败</h2><pre>{result['error']}</pre>")

    return render_template("report.html", request=request, result=result)


if __name__ == "__main__":
    import uvicorn
    logger.info("启动服务器: http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
