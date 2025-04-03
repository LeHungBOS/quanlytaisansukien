# app.py - Quản lý tài sản và đơn hàng với FastAPI
from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException, Depends
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

# Authentication
@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    db = SessionLocal()
    user = db.query(UserDB).filter_by(username=username, password=password).first()
    db.close()
    if not user:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Đăng nhập thất bại"})
    request.session["user_id"] = user.id
    request.session["username"] = user.username
    request.session["role"] = user.role
    return RedirectResponse("/", status_code=302)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)

def get_current_user(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")
    db = SessionLocal()
    user = db.query(UserDB).filter_by(id=user_id).first()
    db.close()
    if not user:
        raise HTTPException(status_code=401, detail="Người dùng không tồn tại")
    return user

def require_role(role: str):
    def checker(user: UserDB = Depends(get_current_user)):
        if user.role != role:
            raise HTTPException(status_code=403, detail="Không có quyền truy cập")
        return user
    return checker

# Asset CRUD
@app.get("/assets", response_class=HTMLResponse)
def list_assets(request: Request):
    db = SessionLocal()
    assets = db.query(AssetDB).all()
    db.close()
    return templates.TemplateResponse("assets.html", {"request": request, "assets": assets})

@app.get("/assets/add", response_class=HTMLResponse)
def add_asset_form(request: Request, user: UserDB = Depends(require_role("admin"))):
    return templates.TemplateResponse("asset_form.html", {"request": request})

@app.post("/assets/add")
def add_asset(request: Request, name: str = Form(...), code: str = Form(...), category: str = Form(...), quantity: int = Form(...), description: str = Form(""), image: UploadFile = File(None), user: UserDB = Depends(require_role("admin"))):
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

@app.get("/assets/edit/{asset_id}", response_class=HTMLResponse)
def edit_asset_form(asset_id: str, request: Request, user: UserDB = Depends(require_role("admin"))):
    db = SessionLocal()
    asset = db.query(AssetDB).filter_by(id=asset_id).first()
    db.close()
    return templates.TemplateResponse("asset_form.html", {"request": request, "asset": asset})

@app.post("/assets/edit/{asset_id}")
def edit_asset(asset_id: str, name: str = Form(...), code: str = Form(...), category: str = Form(...), quantity: int = Form(...), description: str = Form(""), user: UserDB = Depends(require_role("admin"))):
    db = SessionLocal()
    asset = db.query(AssetDB).filter_by(id=asset_id).first()
    if asset:
        asset.name = name
        asset.code = code
        asset.category = category
        asset.quantity = quantity
        asset.description = description
        db.commit()
    db.close()
    return RedirectResponse("/assets", status_code=302)

@app.post("/assets/delete/{asset_id}")
def delete_asset(asset_id: str, user: UserDB = Depends(require_role("admin"))):
    db = SessionLocal()
    asset = db.query(AssetDB).filter_by(id=asset_id).first()
    if asset:
        db.delete(asset)
        db.commit()
    db.close()
    return RedirectResponse("/assets", status_code=302)

# Order logic continues below (unchanged)...
