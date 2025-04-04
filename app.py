# app.py - Quản lý tài sản và đơn hàng với FastAPI (có login)
from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import create_engine, Column, String, Integer, Text, Date, Table, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from uuid import uuid4
from datetime import date
import os, csv, io
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "supersecret"))
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# Many-to-Many Relationship Table
order_asset_table = Table(
    "order_asset", Base.metadata,
    Column("order_id", String, ForeignKey("orders.id")),
    Column("asset_id", String, ForeignKey("assets.id"))
)

# Models
class UserDB(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, index=True)
    username = Column(String, unique=True)
    password = Column(String)
    role = Column(String)

class AssetDB(Base):
    __tablename__ = "assets"
    id = Column(String, primary_key=True, index=True)
    name = Column(String)
    code = Column(String)
    category = Column(String)
    quantity = Column(Integer)
    description = Column(Text)
    image_path = Column(String)
    status = Column(String, default="Sẵn sàng")

class OrderDB(Base):
    __tablename__ = "orders"
    id = Column(String, primary_key=True, index=True)
    customer_name = Column(String)
    start_date = Column(Date)
    end_date = Column(Date)
    status = Column(String, default="Đang cho thuê")
    assets = relationship("AssetDB", secondary=order_asset_table)

Base.metadata.create_all(bind=engine)

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "user": request.session.get("user"), "role": request.session.get("role")})

# ---------------- LOGIN ----------------
@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    db = SessionLocal()
    user = db.query(UserDB).filter_by(username=username, password=password).first()
    db.close()
    if not user:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Sai thông tin đăng nhập"})
    request.session["user"] = user.username
    request.session["role"] = user.role
    return RedirectResponse("/", status_code=302)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")
# ---------------------------------------

@app.get("/assets", response_class=HTMLResponse)
def list_assets(request: Request):
    db = SessionLocal()
    assets = db.query(AssetDB).all()
    db.close()
    return templates.TemplateResponse("assets.html", {"request": request, "assets": assets})

@app.get("/assets/add", response_class=HTMLResponse)
def add_asset_form(request: Request):
    return templates.TemplateResponse("asset_form.html", {"request": request})

@app.post("/assets/add")
def add_asset(request: Request, name: str = Form(...), code: str = Form(...), category: str = Form(...), quantity: int = Form(...), description: str = Form(""), image: UploadFile = File(None)):
    filename = None
    if image:
        filename = f"static/uploads/{uuid4()}_{image.filename}"
        with open(filename, "wb") as f:
            f.write(image.file.read())
    db = SessionLocal()
    asset = AssetDB(id=str(uuid4()), name=name, code=code, category=category, quantity=quantity, description=description, image_path=filename)
    db.add(asset)
    db.commit()
    db.close()
    return RedirectResponse("/assets", status_code=302)

@app.get("/orders", response_class=HTMLResponse)
def list_orders(request: Request):
    db = SessionLocal()
    orders = db.query(OrderDB).all()
    db.close()
    return templates.TemplateResponse("orders.html", {"request": request, "orders": orders})

@app.get("/orders/add", response_class=HTMLResponse)
def add_order_form(request: Request):
    db = SessionLocal()
    all_assets = db.query(AssetDB).filter(AssetDB.status == "Sẵn sàng").all()
    db.close()
    return templates.TemplateResponse("order_detail.html", {"request": request, "all_assets": all_assets})

@app.post("/orders/add")
def add_order(request: Request, customer_name: str = Form(...), start_date: date = Form(...), end_date: date = Form(...), asset_ids: list[str] = Form(...)):
    db = SessionLocal()
    assets = db.query(AssetDB).filter(AssetDB.id.in_(asset_ids)).all()
    for asset in assets:
        asset.status = "Đang cho thuê"
    order = OrderDB(id=str(uuid4()), customer_name=customer_name, start_date=start_date, end_date=end_date, assets=assets)
    db.add(order)
    db.commit()
    db.close()
    return RedirectResponse("/orders", status_code=302)

@app.get("/orders/{order_id}", response_class=HTMLResponse)
def view_order(request: Request, order_id: str):
    db = SessionLocal()
    order = db.query(OrderDB).filter_by(id=order_id).first()
    all_assets = db.query(AssetDB).all()
    db.close()
    return templates.TemplateResponse("order_detail.html", {"request": request, "order": order, "assets": order.assets, "all_assets": all_assets})

@app.post("/orders/status/{order_id}")
def update_order_status(order_id: str, new_status: str = Form(...)):
    db = SessionLocal()
    order = db.query(OrderDB).filter_by(id=order_id).first()
    if order:
        order.status = new_status
        if new_status in ["Hoàn tất", "Đã hủy"]:
            for asset in order.assets:
                asset.status = "Sẵn sàng"
        db.commit()
    db.close()
    return RedirectResponse(f"/orders/{order_id}", status_code=302)

@app.get("/assets/export")
def export_assets():
    db = SessionLocal()
    assets = db.query(AssetDB).all()
    db.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Tên", "Mã", "Danh mục", "Số lượng", "Tình trạng"])
    for asset in assets:
        writer.writerow([asset.id, asset.name, asset.code, asset.category, asset.quantity, asset.status])
    output.seek(0)
    return StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8")), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=assets.csv"})

