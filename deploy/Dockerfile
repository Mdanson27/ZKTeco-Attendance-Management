FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && groupadd --gid 10001 attendance && useradd --uid 10001 --gid 10001 --no-create-home attendance
COPY backend/ /app/backend/
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD ["python","-c","import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=3).read()"]
CMD ["uvicorn","backend.receiver:app","--host","0.0.0.0","--port","8000","--no-proxy-headers","--no-access-log","--limit-concurrency","100","--timeout-keep-alive","5"]
