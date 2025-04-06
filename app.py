# app.py - Toàn bộ mã nguồn đầy đủ chức năng FastAPI app
from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import create_engine, Column, String, Integer, Text, Date, Table, ForeignKey, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from uuid import uuid4
from datetime import date
import os, csv, io
from dotenv import load_dotenv
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import bcrypt

load_dotenv()

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "supersecret"))
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

DATABASE_URL = os.getenv("postgresql://postgres:etjlFARnCMmVDcAVokkRqunFToVHAvHM@postgres.railway.internal:5432/railway")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL chưa được định nghĩa")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

order_asset_table = Table(
    "order_asset", Base.metadata,
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

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": request.session.get("user"),
        "role": request.session.get("role")
    })

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
    request.session["_flash"] = {"success": "Đăng nhập thành công"}
    return RedirectResponse("/", status_code=302)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/")

@app.get("/scan", response_class=HTMLResponse)
def scan_page(request: Request):
    return templates.TemplateResponse("scan.html", {"request": request})

@app.post("/scan")
def scan_result(request: Request, scanned_code: str = Form(...)):
    db = SessionLocal()
    asset = db.query(AssetDB).filter((AssetDB.id == scanned_code) | (AssetDB.code == scanned_code)).first()
    if asset:
        db.close()
        return RedirectResponse(f"/assets?code={asset.code}", status_code=302)
    order = db.query(OrderDB).filter(OrderDB.id == scanned_code).first()
    db.close()
    if order:
        return RedirectResponse(f"/orders/{order.id}", status_code=302)
    return templates.TemplateResponse("scan.html", {"request": request, "error": "Không tìm thấy thiết bị hoặc đơn hàng."})

@app.get("/orders/export/{order_id}")
def export_order_pdf(order_id: str):
    db = SessionLocal()
    order = db.query(OrderDB).filter_by(id=order_id).first()
    db.close()
    if not order:
        raise HTTPException(status_code=404)
    buf = io.BytesIO()
    p = canvas.Canvas(buf, pagesize=A4)
    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, 800, f"Đơn hàng: {order.id}")
    p.setFont("Helvetica", 12)
    p.drawString(50, 780, f"Khách hàng: {order.customer_name}")
    p.drawString(50, 760, f"Từ ngày: {order.start_date} đến {order.end_date}")
    p.drawString(50, 740, f"Trạng thái: {order.status}")
    y = 720
    for a in order.assets:
        p.drawString(60, y, f"- {a.name} ({a.code})")
        y -= 20
    p.save()
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=order_{order_id}.pdf"})

@app.get("/stats", response_class=HTMLResponse)
def statistics_dashboard(request: Request):
    db = SessionLocal()
    asset_total = db.query(AssetDB).count()
    order_total = db.query(OrderDB).count()
    monthly_orders = db.query(
        func.date_trunc('month', OrderDB.start_date).label("month"),
        func.count(OrderDB.id)
    ).group_by("month").order_by("month").all()
    status_counts = db.query(AssetDB.status, func.count()).group_by(AssetDB.status).all()
    db.close()
    return templates.TemplateResponse("stats.html", {
        "request": request,
        "asset_total": asset_total,
        "order_total": order_total,
        "monthly_orders": monthly_orders,
        "status_counts": status_counts
    })
