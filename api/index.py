try:
    from app.main import app
except Exception as e:
    import traceback
    error_detail = traceback.format_exc()

    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    app = FastAPI()

    @app.get("/{path:path}")
    @app.post("/{path:path}")
    async def error_handler(path: str = ""):
        return JSONResponse(
            status_code=500,
            content={
                "error": str(e),
                "traceback": error_detail
            }
        )
