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
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:etjlFARnCMmVDcAVokkRqunFToVHAvHM@postgres.railway.internal:5432/railway")
engine = create_engine(DATABASE_URL)
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

# Auto-create default admin if none exists
def create_default_admin():
    db = SessionLocal()
    if not db.query(UserDB).filter_by(username="admin").first():
        admin = UserDB(id=str(uuid4()), username="admin", password="admin", role="admin")
        db.add(admin)
        db.commit()
    db.close()

create_default_admin()

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

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

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

from fastapi.responses import FileResponse
import qrcode
from barcode import Code128
from barcode.writer import ImageWriter

@app.get("/assets/barcode/{asset_id}")
def barcode_image(asset_id: str):
    path = f"static/barcodes/{asset_id}.png"
    if not os.path.exists(path):
        barcode = Code128(asset_id, writer=ImageWriter())
        barcode.save(path[:-4])
    return FileResponse(path)

@app.get("/assets/qrcode/{asset_id}")
def qrcode_image(asset_id: str):
    path = f"static/qrcodes/{asset_id}.png"
    if not os.path.exists(path):
        img = qrcode.make(asset_id)
        img.save(path)
    return FileResponse(path)

@app.get("/assets/view/{asset_id}", response_class=HTMLResponse)
def view_asset(asset_id: str, request: Request):
    db = SessionLocal()
    asset = db.query(AssetDB).filter_by(id=asset_id).first()
    db.close()
    if not asset:
        raise HTTPException(status_code=404, detail="Tài sản không tồn tại")
    return templates.TemplateResponse("asset_detail.html", {"request": request, "asset": asset})
@app.get("/assets", response_class=HTMLResponse)
def list_assets(request: Request):
    db = SessionLocal()
    query = db.query(AssetDB)

    search = request.query_params.get("search")
    category = request.query_params.get("category")
    status = request.query_params.get("status")

    if search:
        query = query.filter(AssetDB.name.ilike(f"%{search}%"))
    if category:
        query = query.filter(AssetDB.category == category)
    if status:
        query = query.filter(AssetDB.status == status)

    assets = query.all()
    categories = db.query(AssetDB.category).distinct().all()
    db.close()

    category_list = sorted(set(cat[0] for cat in categories if cat[0]))
    return templates.TemplateResponse("assets.html", {
        "request": request,
        "assets": assets,
        "search": search,
        "category": category,
        "status": status,
        "categories": category_list
    })
def list_assets(request: Request):
    db = SessionLocal()
    query = db.query(AssetDB)

    search = request.query_params.get("search")
    category = request.query_params.get("category")
    status = request.query_params.get("status")

    if search:
        query = query.filter(AssetDB.name.ilike(f"%{search}%"))
    if category:
        query = query.filter(AssetDB.category == category)
    if status:
        query = query.filter(AssetDB.status == status)

    assets = query.all()
    print(f"📦 Tổng số tài sản trong DB sau lọc: {len(assets)}")
    db.close()
    return templates.TemplateResponse("assets.html", {"request": request, "assets": assets, "search": search, "category": category, "status": status})

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
def edit_asset(asset_id: str, name: str = Form(...), code: str = Form(...), category: str = Form(...), quantity: int = Form(...), status: str = Form(...), description: str = Form(""), user: UserDB = Depends(require_role("admin"))):
    db = SessionLocal()
    asset = db.query(AssetDB).filter_by(id=asset_id).first()
    if asset:
        asset.name = name
        asset.code = code
        asset.category = category
        asset.quantity = quantity
        asset.status = status
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

@app.get("/assets/export")
def export_assets(user: UserDB = Depends(require_role("admin"))):
    db = SessionLocal()
    assets = db.query(AssetDB).all()
    db.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Tên", "Mã", "Danh mục", "Số lượng", "Tình trạng"])
    for asset in assets:
        writer.writerow([asset.id, asset.name, asset.code, asset.category, asset.quantity, asset.status])
    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8-sig")),  # fix font tiếng Việt
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=assets.csv"}
    )

# Order CRUD
@app.get("/orders", response_class=HTMLResponse)
def list_orders(request: Request):
    db = SessionLocal()
    orders = db.query(OrderDB).all()
    db.close()
    return templates.TemplateResponse("orders.html", {"request": request, "orders": orders})

@app.get("/orders/add", response_class=HTMLResponse)
def add_order_form(request: Request, user: UserDB = Depends(require_role("admin"))):
    db = SessionLocal()
    all_assets = db.query(AssetDB).filter(AssetDB.status == "Sẵn sàng").all()
    db.close()
    return templates.TemplateResponse("order_detail.html", {"request": request, "all_assets": all_assets})

@app.post("/orders/add")
def add_order(request: Request, customer_name: str = Form(...), start_date: date = Form(...), end_date: date = Form(...), asset_ids: list[str] = Form(...), user: UserDB = Depends(require_role("admin"))):
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
def update_order_status(order_id: str, new_status: str = Form(...), user: UserDB = Depends(require_role("admin"))):
    db = SessionLocal()
    order = db.query(OrderDB).filter_by(id=order_id).first()
    if order:
        order.status = new_status
        for asset in order.assets:
            if new_status == "Hoàn tất":
                asset.status = "Sẵn sàng"
            elif new_status == "Đã hủy":
                asset.status = "Chờ xử lý"
            elif new_status == "Bảo trì":
                asset.status = "Bảo trì"
        db.commit()
    db.close()
    return RedirectResponse(f"/orders/{order_id}", status_code=302)

@app.post("/orders/delete/{order_id}")
def delete_order(order_id: str, user: UserDB = Depends(require_role("admin"))):
    db = SessionLocal()
    order = db.query(OrderDB).filter_by(id=order_id).first()
    if order:
        for asset in order.assets:
            asset.status = "Sẵn sàng"
        db.delete(order)
        db.commit()
    db.close()
    return RedirectResponse("/orders", status_code=302)
