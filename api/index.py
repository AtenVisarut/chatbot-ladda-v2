from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI()

@app.get("/")
async def root():
    return {"status": "ok", "message": "minimal test"}

@app.get("/{path:path}")
async def catch_all(path: str):
    return {"status": "ok", "path": path}

@app.post("/{path:path}")
async def catch_all_post(path: str):
    return {"status": "ok", "path": path}
