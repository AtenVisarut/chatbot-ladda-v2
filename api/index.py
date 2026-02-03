import json
import sys

# Step 1: Try a minimal response first
startup_error = None

try:
    from app.main import app
except Exception as e:
    import traceback
    startup_error = {
        "error": str(e),
        "type": type(e).__name__,
        "traceback": traceback.format_exc(),
        "python_version": sys.version
    }

    # Fallback: minimal ASGI app
    async def app(scope, receive, send):
        if scope["type"] == "http":
            body = json.dumps(startup_error, ensure_ascii=False).encode("utf-8")
            await send({
                "type": "http.response.start",
                "status": 500,
                "headers": [
                    [b"content-type", b"application/json; charset=utf-8"],
                ],
            })
            await send({
                "type": "http.response.body",
                "body": body,
            })
