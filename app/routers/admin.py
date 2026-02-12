import logging
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.config import ADMIN_USERNAME, ADMIN_PASSWORD, EMBEDDING_MODEL
from app.dependencies import openai_client, supabase_client
from app.services.cache import clear_all_caches

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="templates")


class LoginRequest(BaseModel):
    username: str
    password: str


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
async def login(request: Request, login_data: LoginRequest):
    if login_data.username == ADMIN_USERNAME and login_data.password == ADMIN_PASSWORD:
        request.session["user"] = "admin"
        return {"status": "success", "message": "Login successful"}
    else:
        return JSONResponse(
            status_code=401,
            content={"status": "error", "message": "Invalid username or password"}
        )


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login")


@router.post("/cache/clear")
async def clear_cache_endpoint(request: Request):
    await clear_all_caches()
    return {"status": "success", "message": "All caches cleared"}


@router.post("/admin/regenerate-embeddings")
async def regenerate_embeddings_endpoint(request: Request):
    """
    Regenerate embeddings for products after data changes.
    Body (optional): {"product_name": "อาร์เทมิส"}  — regenerate one product
    Body empty or {}                                  — regenerate ALL products
    """
    if not request.session.get("user"):
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not openai_client or not supabase_client:
        raise HTTPException(status_code=503, detail="OpenAI or Supabase not available")

    try:
        body = await request.json()
    except Exception:
        body = {}

    product_name = body.get("product_name")

    # Fetch products to regenerate
    if product_name:
        result = supabase_client.table('products').select('*').ilike('product_name', f'%{product_name}%').execute()
    else:
        result = supabase_client.table('products').select('*').execute()

    if not result.data:
        return {"status": "error", "message": f"ไม่พบสินค้า: {product_name}" if product_name else "ไม่พบสินค้าในระบบ"}

    products = result.data
    success_count = 0
    errors = []

    for product in products:
        try:
            text_parts = [
                f"ชื่อสินค้า: {product['product_name']}",
                f"สารสำคัญ: {product.get('active_ingredient', '')}",
                f"ศัตรูพืชที่กำจัดได้: {product.get('target_pest', '')}",
                f"ใช้ได้กับพืช: {product.get('applicable_crops', '')}",
                f"กลุ่มสาร: {product.get('product_group', '')}",
            ]
            text = " | ".join([p for p in text_parts if p])

            resp = await openai_client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=text
            )
            embedding = resp.data[0].embedding

            supabase_client.table('products').update({
                'embedding': embedding
            }).eq('id', product['id']).execute()

            success_count += 1
        except Exception as e:
            errors.append(f"{product['product_name']}: {str(e)}")

    # Clear caches so new embeddings take effect immediately
    await clear_all_caches()

    return {
        "status": "success",
        "regenerated": success_count,
        "total": len(products),
        "errors": errors if errors else None,
        "cache_cleared": True
    }
