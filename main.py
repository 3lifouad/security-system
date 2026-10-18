import os
import uuid
import sqlite3
import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.colormasks import SolidFillColorMask

from fastapi import FastAPI, HTTPException, Request, Form, File, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse

app = FastAPI(title="Security Clearance System")

# إنشاء المجلدات المطلوبة تلقائياً
os.makedirs("static", exist_ok=True)
os.makedirs("uploads", exist_ok=True)

# ربط الملفات الثابتة والقوالب
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# دالة توليد الـ QR Code الأزرق المخصص
def generate_custom_qr(permit_uuid: str, base_url: str = "http://127.0.0.1:8000"):
    target_url = f"{base_url}/qr/{permit_uuid}"
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(target_url)
    qr.make(fit=True)

    img = qr.make_image(
        image_factory=StyledPilImage,
        color_mask=SolidFillColorMask(
            back_color=(255, 255, 255),
            front_color=(0, 102, 204)  # لون الباركود الأزرق
        )
    )
    
    qr_filename = f"qr_{permit_uuid}.png"
    qr_path = os.path.join("static", qr_filename)
    img.save(qr_path)
    return qr_filename

# 1. صفحة لوحة التحكم /admin
@app.get("/admin")
async def admin_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={"success": False}
    )

# 2. معالجة نموذج الإدخال ورفع الملفات
@app.post("/admin/add")
async def add_permit(
    request: Request,
    permit_number: str = Form(...),
    company_name: str = Form(...),
    issue_date: str = Form(...),
    expiry_date: str = Form(...),
    pdf_file: UploadFile = File(...)
):
    permit_uuid = str(uuid.uuid4())
    
    # حفظ ملف الـ PDF
    pdf_filename = f"{permit_uuid}_{pdf_file.filename}"
    pdf_path = os.path.join("uploads", pdf_filename)
    
    content = await pdf_file.read()
    with open(pdf_path, "wb") as f:
        f.write(content)

    # حفظ البيانات في SQLite
    conn = sqlite3.connect("permits.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS permits (
            uuid TEXT PRIMARY KEY,
            permit_number TEXT,
            company_name TEXT,
            issue_date TEXT,
            expiry_date TEXT,
            pdf_filename TEXT
        )
    """)
    cursor.execute("""
        INSERT INTO permits (uuid, permit_number, company_name, issue_date, expiry_date, pdf_filename)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (permit_uuid, permit_number, company_name, issue_date, expiry_date, pdf_filename))
    conn.commit()
    conn.close()

    # توليد صورة الباركود
    qr_filename = generate_custom_qr(permit_uuid, base_url="http://127.0.0.1:8000")

    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "success": True,
            "qr_filename": qr_filename,
            "permit_uuid": permit_uuid
        }
    )

# 3. عرض التصريح عند مسح الـ QR
@app.get("/qr/{permit_uuid}")
async def view_permit(request: Request, permit_uuid: str):
    conn = sqlite3.connect("permits.db")
    cursor = conn.cursor()
    cursor.execute("SELECT uuid, permit_number, company_name, issue_date, expiry_date, pdf_filename FROM permits WHERE uuid = ?", (permit_uuid,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="التصريح غير موجود")

    permit_data = {
        "uuid": row[0],
        "permit_number": row[1],
        "company_name": row[2],
        "issue_date": row[3],
        "expiry_date": row[4],
        "pdf_filename": row[5]
    }

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"permit": permit_data}
    )

# 4. تنزيل ملف الـ PDF
@app.get("/download/{permit_uuid}")
async def download_pdf(permit_uuid: str):
    conn = sqlite3.connect("permits.db")
    cursor = conn.cursor()
    cursor.execute("SELECT pdf_filename FROM permits WHERE uuid = ?", (permit_uuid,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="الملف غير موجود")

    pdf_path = os.path.join("uploads", row[0])
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="ملف الـ PDF غير متوفر")

    return FileResponse(pdf_path, filename=row[0], media_type="application/pdf")