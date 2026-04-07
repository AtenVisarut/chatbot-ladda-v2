web: gunicorn app.main:app -w ${WEB_CONCURRENCY:-8} -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-8080} --timeout 120 --graceful-timeout 30
