# ============================================
# RFM 分析报告 — Docker 打包说明书
# ============================================
# 这个文件告诉 Docker："怎么搭一个能跑 RFM 报告的环境"
#
# 每一行就是一步指令，从上到下执行
# ============================================

# 第1步：选基础镜像（"买一个灶台"）
# python:3.14-slim = 精简版 Python 3.14，只有 150MB
FROM docker.m.daocloud.io/library/python:3.14-slim

# 第2步：设工作目录（"在厨房里划一块台面"）
# 后面所有操作都在 /app 这个目录下进行
WORKDIR /app

# 第3步：装系统依赖（"先接通水电"）
# python-multipart 需要 libmagic
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# 第4步：复制 Python 依赖清单（"先拿调料清单"）
# 单独复制 requirements.txt 可以利用 Docker 缓存：
#   只要清单不变，Docker 就复用上一版，不需要重装
COPY requirements.txt .

# 第5步：装 Python 依赖（"按清单买调料"）
RUN pip install --no-cache-dir -r requirements.txt

# 第6步：复制项目文件（"把菜谱搬进来"）
COPY server.py analysis.py database.py .
COPY templates/ templates/
COPY static/ static/

# 第7步：暴露端口（"告诉客人从哪个门进来"）
# 8001 = RFM 报告的端口
EXPOSE 8001

# 第8步：启动命令（"点火开张"）
CMD ["python", "server.py"]
