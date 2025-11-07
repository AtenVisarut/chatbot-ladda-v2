#!/usr/bin/env python
"""
Test all required imports for LINE Plant Disease Detection Bot
Run this to verify all dependencies are installed correctly
"""

import sys

print("=" * 60)
print("Testing Python Environment")
print("=" * 60)
print(f"Python Version: {sys.version}")
print(f"Python Path: {sys.executable}")
print()

print("=" * 60)
print("Testing Package Imports")
print("=" * 60)

success_count = 0
total_count = 0

def test_import(package_name, import_statement):
    """Test a single import"""
    global success_count, total_count
    total_count += 1
    try:
        exec(import_statement)
        print(f"✅ {package_name}")
        success_count += 1
        return True
    except ImportError as e:
        print(f"❌ {package_name}: {e}")
        return False
    except Exception as e:
        print(f"⚠️  {package_name}: {e}")
        return False

# Test all required packages
test_import("FastAPI", "from fastapi import FastAPI")
test_import("Uvicorn", "import uvicorn")
test_import("Pydantic", "from pydantic import BaseModel")
test_import("httpx", "import httpx")
test_import("Pinecone", "from pinecone import Pinecone, ServerlessSpec")
test_import("Google Generative AI", "import google.generativeai as genai")
test_import("Pillow (PIL)", "from PIL import Image")
test_import("python-dotenv", "from dotenv import load_dotenv")
test_import("requests", "import requests")

print()
print("=" * 60)
print(f"Results: {success_count}/{total_count} packages imported successfully")
print("=" * 60)

if success_count == total_count:
    print("✅ All dependencies are installed correctly!")
    print("You can now run: python main.py")
    sys.exit(0)
else:
    print("❌ Some dependencies are missing")
    print("Please run: pip install -r requirements.txt")
    sys.exit(1)
