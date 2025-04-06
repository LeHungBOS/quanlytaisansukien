# ✅ app.py - FASTAPI HOÀN CHỈNH
# Đầy đủ chức năng: đăng nhập, phân quyền, đơn hàng, thiết bị, QR/Barcode, thống kê, PDF, logs
from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import create_engine, Column, String, Integer, Text, Date, Table, ForeignKey, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from uuid import uuid4
from datetime import date
import os, csv, io, bcrypt
from dotenv import load_dotenv
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

load_dotenv()

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "supersecret"))

# Route favicon.ico để tránh lỗi 500
@app.get("/favicon.ico", include_in_schema=False)
def ignore_favicon():
    return HTMLResponse("", status_code=204)
    return HTMLResponse("", status_code=204)

@app.middleware("http")
async def ensure_session_support(request: Request, call_next):
    if "session" not in request.scope:
        return HTMLResponse("Lỗi hệ thống: SessionMiddleware chưa được cấu hình.", status_code=500)
    return await call_next(request)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

order_asset_table = Table("order_asset", Base.metadata,
    Column("order_id", String, ForeignKey("orders.id")),
    Column("asset_id", String, ForeignKey("assets.id"))
)

class UserDB(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True)
    username = Column(String, unique=True)
    password = Column(String)
    role = Column(String)

class AssetDB(Base):
    __tablename__ = "assets"
    id = Column(String, primary_key=True)
    name = Column(String)
    code = Column(String)
    category = Column(String)
    quantity = Column(Integer)
    description = Column(Text)
    image_path = Column(String)
    status = Column(String, default="Sẵn sàng")

class OrderDB(Base):
    __tablename__ = "orders"
    id = Column(String, primary_key=True)
    customer_name = Column(String)
    start_date = Column(Date)
    end_date = Column(Date)
    status = Column(String)
    assets = relationship("AssetDB", secondary=order_asset_table)

class AssetLogDB(Base):
    __tablename__ = "asset_logs"
    id = Column(String, primary_key=True)
    asset_id = Column(String)
    action = Column(String)
    note = Column(Text)
    timestamp = Column(Date)

Base.metadata.create_all(bind=engine)

@app.middleware("http")
async def require_login(request: Request, call_next):
    if request.url.path not in ("/login", "/logout", "/scan") and not request.url.path.startswith("/static"):
        if not request.session.get("user"):
            return RedirectResponse("/login")
    response = await call_next(request)
    if "_flash" in request.session:
        request.session["flash"] = request.session.pop("_flash")
    return response

@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    db = SessionLocal()
    user = db.query(UserDB).filter_by(username=username).first()
    db.close()
    if not user or not bcrypt.checkpw(password.encode(), user.password.encode()):
        request.session["_flash"] = {"error": "Sai thông tin đăng nhập"}
        return RedirectResponse("/login", status_code=302)
    request.session["user"] = user.username
    request.session["role"] = user.role
    return RedirectResponse("/", status_code=302)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/")

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    try:
        return templates.TemplateResponse("index.html", {
            "request": request,
            "user": request.session.get("user"),
            "role": request.session.get("role")
        })
    except Exception as e:
        return HTMLResponse(content=f"<h2>Lỗi: {str(e)}</h2>", status_code=500)
