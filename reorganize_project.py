#!/usr/bin/env python
"""
สคริปต์จัดระเบียบโครงสร้าง project
รันไฟล์นี้เพื่อย้ายไฟล์ไปยังโฟลเดอร์ที่เหมาะสม
"""

import os
import shutil

def create_folders():
    """สร้างโฟลเดอร์ทั้งหมด"""
    folders = [
        'app',           # โค้ดหลัก
        'docs',          # เอกสาร
        'tests',         # ไฟล์ทดสอบ
        'scripts',       # สคริปต์ setup
        'config',        # ไฟล์ config
        'data',          # ข้อมูล
    ]
    
    for folder in folders:
        os.makedirs(folder, exist_ok=True)
        print(f"✅ สร้างโฟลเดอร์: {folder}/")
    
    # สร้าง __init__.py สำหรับ app
    with open('app/__init__.py', 'w', encoding='utf-8') as f:
        f.write('"""LINE Plant Disease Detection Bot"""\n')
    print("✅ สร้าง app/__init__.py")

def move_files():
    """ย้ายไฟล์ไปยังโฟลเดอร์ที่เหมาะสม"""
    
    moves = {
        # เอกสาร
        'docs': [
            'README.md',
            'START_HERE.md',
            'INSTALL.md',
            'DEPLOYMENT.md',
            'ARCHITECTURE.md',
            'PROJECT_SUMMARY.md',
            'PAYLOAD_EXAMPLES.md',
            'TROUBLESHOOTING.md',
            'QUICK_REFERENCE.md',
            'PYTHON_313_NOTES.md',
            'OPENAI_SETUP.md',
            'NGROK_SETUP.md',
            'FIX_PINECONE.md',
            'STATUS.md',
            'INDEX.md',
        ],
        
        # ไฟล์ทดสอบ
        'tests': [
            'test_webhook.py',
            'test_gemini.py',
            'test_openai.py',
            'test_line_image.py',
            'test_imports.py',
            'quick_test.py',
        ],
        
        # สคริปต์ setup
        'scripts': [
            'setup_pinecone.py',
            'populate_products.py',
            'quickstart.sh',
            'quickstart.bat',
        ],
        
        # Config
        'config': [
            '.env.example',
        ],
    }
    
    for folder, files in moves.items():
        for file in files:
            if os.path.exists(file):
                try:
                    shutil.move(file, f"{folder}/{file}")
                    print(f"✅ ย้าย {file} → {folder}/")
                except Exception as e:
                    print(f"⚠️  ไม่สามารถย้าย {file}: {e}")

def create_app_structure():
    """สร้างโครงสร้างโค้ดใน app/"""
    
    # ย้าย main.py
    if os.path.exists('main.py'):
        shutil.copy('main.py', 'app/main.py')
        print("✅ คัดลอก main.py → app/main.py")
    
    print("\n📝 หมายเหตุ: main.py ต้นฉบับยังอยู่ที่เดิม")
    print("   ถ้าต้องการใช้โครงสร้างใหม่ ให้รัน: python app/main.py")

def create_readme():
    """สร้าง README ใหม่ที่ root"""
    
    readme_content = """# 🌱 LINE Plant Disease Detection Bot

AI-powered chatbot สำหรับตรวจสอบโรคพืชและแนะนำผลิตภัณฑ์

## 📁 โครงสร้าง Project

```
.
├── app/                    # โค้ดหลักของแอปพลิเคชัน
│   ├── __init__.py
│   └── main.py            # FastAPI application
│
├── docs/                   # เอกสารทั้งหมด
│   ├── START_HERE.md      # เริ่มต้นที่นี่
│   ├── INSTALL.md         # คู่มือติดตั้ง
│   ├── DEPLOYMENT.md      # คู่มือ deploy
│   └── ...
│
├── tests/                  # ไฟล์ทดสอบ
│   ├── test_webhook.py
│   ├── test_openai.py
│   └── ...
│
├── scripts/                # สคริปต์ setup และ utility
│   ├── setup_pinecone.py
│   ├── populate_products.py
│   └── ...
│
├── config/                 # ไฟล์ config
│   └── .env.example
│
├── data/                   # ข้อมูล (ถ้ามี)
│
├── .env                    # Environment variables (ไม่ commit)
├── .gitignore
├── requirements.txt
├── Dockerfile
└── README.md              # ไฟล์นี้
```

## 🚀 Quick Start

```bash
# 1. ติดตั้ง dependencies
pip install -r requirements.txt

# 2. ตั้งค่า environment
cp config/.env.example .env
# แก้ไข .env ใส่ API keys

# 3. Setup Pinecone
python scripts/setup_pinecone.py
python scripts/populate_products.py

# 4. รัน server
python app/main.py
```

## 📚 เอกสาร

- **เริ่มต้น:** [docs/START_HERE.md](docs/START_HERE.md)
- **ติดตั้ง:** [docs/INSTALL.md](docs/INSTALL.md)
- **Deploy:** [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
- **แก้ปัญหา:** [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)

## 🧪 ทดสอบ

```bash
# ทดสอบ OpenAI
python tests/test_openai.py

# ทดสอบ webhook
python tests/test_webhook.py

# ทดสอบทั้งหมด
python tests/quick_test.py
```

## 📝 License

MIT License

---

**อ่านเอกสารเพิ่มเติมใน [docs/](docs/) folder**
"""
    
    with open('README_NEW.md', 'w', encoding='utf-8') as f:
        f.write(readme_content)
    
    print("\n✅ สร้าง README_NEW.md")

def main():
    """รันการจัดระเบียบทั้งหมด"""
    
    print("="*60)
    print("🗂️  จัดระเบียบโครงสร้าง Project")
    print("="*60)
    print()
    
    # ยืนยันก่อนดำเนินการ
    print("⚠️  สคริปต์นี้จะย้ายไฟล์ไปยังโฟลเดอร์ใหม่")
    print("   แนะนำให้ backup project ก่อน")
    print()
    
    response = input("ดำเนินการต่อ? (yes/no): ")
    
    if response.lower() != 'yes':
        print("❌ ยกเลิกการดำเนินการ")
        return
    
    print("\n🚀 เริ่มจัดระเบียบ...\n")
    
    # สร้างโฟลเดอร์
    print("📁 สร้างโฟลเดอร์...")
    create_folders()
    
    print("\n📦 ย้ายไฟล์...")
    move_files()
    
    print("\n🏗️  สร้างโครงสร้าง app/...")
    create_app_structure()
    
    print("\n📝 สร้าง README ใหม่...")
    create_readme()
    
    print("\n" + "="*60)
    print("✅ จัดระเบียบเสร็จสิ้น!")
    print("="*60)
    
    print("\n📋 โครงสร้างใหม่:")
    print("""
    ├── app/           # โค้ดหลัก
    ├── docs/          # เอกสาร
    ├── tests/         # ทดสอบ
    ├── scripts/       # setup scripts
    ├── config/        # config files
    └── data/          # ข้อมูล
    """)
    
    print("\n🎯 ขั้นตอนต่อไป:")
    print("1. ตรวจสอบว่าไฟล์ย้ายถูกต้อง")
    print("2. ลบไฟล์เก่าที่ไม่ต้องการ")
    print("3. เปลี่ยนชื่อ README_NEW.md → README.md")
    print("4. รัน server: python app/main.py")
    print()
    print("💡 ถ้าต้องการใช้โครงสร้างเดิม:")
    print("   - ไฟล์ต้นฉบับยังอยู่ที่เดิม")
    print("   - สามารถลบโฟลเดอร์ใหม่ได้")

if __name__ == "__main__":
    main()
