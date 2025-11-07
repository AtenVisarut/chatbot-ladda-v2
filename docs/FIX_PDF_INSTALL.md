# 🔧 แก้ปัญหาการติดตั้ง PDF Support

## ❌ ปัญหา: ติดตั้ง requirements.txt ไม่ได้

### สาเหตุ
- Python 3.13 มีปัญหากับ package บางตัว
- pandas ต้องการ build tools

---

## ✅ วิธีแก้ไข

### วิธีที่ 1: ติดตั้งเฉพาะ PDF Support (แนะนำ)

**Windows:**
```bash
install_pdf_support.bat
```

**Linux/Mac:**
```bash
chmod +x install_pdf_support.sh
./install_pdf_support.sh
```

**หรือติดตั้งเอง:**
```bash
pip install pdfplumber==0.11.4
pip install pypdf==4.0.1
```

---

### วิธีที่ 2: ติดตั้งทีละ package

```bash
# ติดตั้งเฉพาะที่จำเป็น
pip install fastapi==0.115.0
pip install uvicorn[standard]==0.32.0
pip install pydantic==2.9.2
pip install httpx==0.27.2
pip install openai==1.54.0
pip install pinecone==5.4.2
pip install Pillow==11.0.0
pip install python-dotenv==1.0.1
pip install python-multipart==0.0.12
pip install requests==2.32.3

# สำหรับ PDF (ถ้าต้องการ)
pip install pdfplumber==0.11.4
pip install pypdf==4.0.1
```

---

### วิธีที่ 3: ข้าม pandas

แก้ไข `requirements.txt`:
```txt
# ลบหรือ comment บรรทัดนี้
# pandas==2.2.0
```

แล้วรัน:
```bash
pip install -r requirements.txt
```

---

## 🧪 ทดสอบว่าติดตั้งสำเร็จ

```bash
python -c "import pdfplumber; print('✅ pdfplumber OK')"
```

ควรเห็น:
```
✅ pdfplumber OK
```

---

## 📊 ใช้งาน PDF

### ดู PDF
```bash
python scripts/preview_pdf.py
```

### Import จาก PDF
```bash
python scripts/import_pdf_to_pinecone.py
```

---

## 🔄 ทางเลือก: ใช้ CSV แทน

ถ้าติดตั้ง PDF support ไม่ได้ แนะนำให้:

1. **แปลง PDF เป็น CSV**
   - เปิด PDF ด้วย Excel/Google Sheets
   - Export เป็น CSV
   
2. **ใช้ CSV Import**
   ```bash
   python scripts/import_csv_to_pinecone.py
   ```

**ข้อดี:**
- ✅ ไม่ต้องติดตั้ง PDF libraries
- ✅ ความแม่นยำสูงกว่า
- ✅ แก้ไขข้อมูลได้ง่าย

---

## 💡 สำหรับ Python 3.13

ถ้ายังมีปัญหา แนะนำให้:

### ตัวเลือกที่ 1: ใช้ Python 3.11 หรือ 3.12

```bash
# ติดตั้ง Python 3.12
# จาก python.org

# สร้าง virtual environment
python3.12 -m venv venv
venv\Scripts\activate  # Windows
# หรือ
source venv/bin/activate  # Linux/Mac

# ติดตั้ง packages
pip install -r requirements.txt
```

---

### ตัวเลือกที่ 2: ใช้ conda

```bash
conda create -n linebot python=3.12
conda activate linebot
pip install -r requirements.txt
```

---

## 📋 Checklist

- [ ] ลอง `install_pdf_support.bat` (Windows)
- [ ] หรือ `pip install pdfplumber pypdf`
- [ ] ทดสอบ `python -c "import pdfplumber"`
- [ ] ถ้าไม่ได้ → แปลง PDF เป็น CSV
- [ ] ใช้ `import_csv_to_pinecone.py` แทน

---

## 🆘 ยังแก้ไม่ได้?

**ใช้ CSV แทน PDF:**

1. เปิด PDF ด้วย Adobe Reader
2. Copy ข้อความ
3. Paste ใน Excel
4. Save as CSV
5. รัน `python scripts/import_csv_to_pinecone.py`

**หรือใช้ Online Tools:**
- https://www.ilovepdf.com/pdf_to_excel
- https://smallpdf.com/pdf-to-excel
- แปลง PDF → Excel → CSV

---

**แนะนำ: ใช้ CSV จะง่ายและแม่นยำกว่า!** 📊
