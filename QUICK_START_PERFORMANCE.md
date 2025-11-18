# ⚡ Quick Start - Performance Testing

เริ่มต้นทดสอบ Performance ใน 5 นาที

## 🚀 ขั้นตอนที่ 1: ติดตั้ง Dependencies

```bash
# ติดตั้ง slowapi สำหรับ rate limiting
pip install slowapi==0.1.9

# ติดตั้ง aiohttp สำหรับ load testing
pip install aiohttp
```

## 🏃 ขั้นตอนที่ 2: เริ่ม Server

```bash
# Terminal 1: Start server
python app/main.py
```

รอจนเห็น:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Starting background tasks...
```

## 🧪 ขั้นตอนที่ 3: ทดสอบ Features

### 3.1 ทดสอบ Health Check

```bash
curl http://localhost:8000/health
```

**ผลลัพธ์ที่คาดหวัง:**
```json
{
  "status": "healthy",
  "services": {
    "gemini": "ok",
    "supabase": "ok",
    "line": "ok"
  },
  "cache": {
    "detection_cache_size": 0,
    "product_cache_size": 0,
    "knowledge_cache_size": 0,
    "pending_contexts": 0,
    "total_memory_items": 0
  },
  "rate_limiting": {
    "active_users": 0,
    "user_limit": "10 requests per 60s"
  }
}
```

### 3.2 ทดสอบ Cache Stats

```bash
curl http://localhost:8000/cache/stats
```

**ผลลัพธ์ที่คาดหวัง:**
```json
{
  "cache_stats": {
    "detection_cache_size": 0,
    "product_cache_size": 0,
    "knowledge_cache_size": 0,
    "pending_contexts": 0,
    "total_memory_items": 0
  },
  "cache_config": {
    "ttl_seconds": 3600,
    "max_size": 1000,
    "pending_context_ttl": 300
  },
  "rate_limiting": {
    "active_users": 0,
    "user_limit": 10,
    "window_seconds": 60
  }
}
```

### 3.3 ทดสอบ Rate Limiting

```bash
# ส่ง requests ติดต่อกัน 15 ครั้ง (เกิน limit)
for i in {1..15}; do
  echo "Request $i:"
  curl -X POST http://localhost:8000/webhook \
    -H "Content-Type: application/json" \
    -d '{
      "events": [{
        "type": "message",
        "replyToken": "test_token_'$i'",
        "source": {"userId": "test_user_123"},
        "message": {"type": "text", "text": "สวัสดี"}
      }]
    }'
  echo ""
  sleep 0.5
done
```

**ผลลัพธ์ที่คาดหวัง:**
- Request 1-10: Status 200 (OK)
- Request 11-15: Status 429 (Rate Limited) หรือได้รับข้อความ rate limit

## 📊 ขั้นตอนที่ 4: รัน Load Test

```bash
# Terminal 2: Run load test
python tests/load_test.py
```

**ผลลัพธ์ที่คาดหวัง:**
```
============================================================
LINE Plant Disease Bot - Load Testing
============================================================
Target: http://localhost:8000
Concurrent Users: 10
Requests per User: 5

Testing Health Endpoint
============================================================
Status: 200
Response Time: 0.123s

Testing Rate Limiting
============================================================
Request 1: Status=200
Request 2: Status=200
...
Request 11: Status=429  ← Rate limited!

✓ Rate limiting working: 5/15 requests blocked

Testing Cache Performance
============================================================
Request 1: 2.345s (Status=200)  ← No cache
Request 2: 0.123s (Status=200)  ← Cached!
Request 3: 0.098s (Status=200)  ← Cached!

✓ Cache Performance:
  First request (no cache): 2.345s
  Avg cached requests: 0.109s
  Performance improvement: 95.4%

Running Concurrent Load Test
============================================================
Total Requests: 50
Successful: 48 (96.0%)
Failed: 2 (4.0%)
Requests/Second: 4.05

Response Time Statistics:
  Min: 0.098s
  Max: 2.456s
  Mean: 0.876s
  Median: 0.654s

✅ Load testing completed!
```

## ✅ ขั้นตอนที่ 5: ตรวจสอบผลลัพธ์

### เกณฑ์การผ่าน:

- ✅ **Health Check**: Status = healthy
- ✅ **Rate Limiting**: Block requests ที่เกิน 10/นาที
- ✅ **Cache**: เร็วขึ้น > 80%
- ✅ **Success Rate**: > 95%
- ✅ **Response Time**: < 2s (avg)

### ถ้าผ่านทุกข้อ:

```
🎉 ยินดีด้วย! ระบบพร้อม Deploy แล้ว
```

### ถ้าไม่ผ่าน:

ดู troubleshooting ใน `tests/LOAD_TESTING.md`

## 🔧 การปรับแต่ง (Optional)

### เพิ่ม Cache Size

```python
# ใน app/main.py (บรรทัด ~100)
MAX_CACHE_SIZE = 2000  # เพิ่มจาก 1000
CACHE_TTL = 7200  # เพิ่มจาก 3600 (2 ชั่วโมง)
```

### เพิ่ม Rate Limit

```python
# ใน app/main.py (บรรทัด ~105)
USER_RATE_LIMIT = 20  # เพิ่มจาก 10
```

### เพิ่ม Concurrent Users ในการทดสอบ

```python
# ใน tests/load_test.py (บรรทัด ~15)
NUM_CONCURRENT_USERS = 20  # เพิ่มจาก 10
REQUESTS_PER_USER = 10  # เพิ่มจาก 5
```

## 📈 ดู Real-time Stats

### ขณะ Server ทำงาน:

```bash
# Terminal 3: Watch cache stats
watch -n 5 'curl -s http://localhost:8000/cache/stats | jq'
```

**จะเห็น:**
```json
{
  "cache_stats": {
    "detection_cache_size": 15,  ← เพิ่มขึ้นเรื่อยๆ
    "product_cache_size": 8,
    "knowledge_cache_size": 12,
    "pending_contexts": 2,
    "total_memory_items": 37
  },
  "rate_limiting": {
    "active_users": 5  ← จำนวน users ที่ active
  }
}
```

## 🧹 Clear Cache (ถ้าต้องการ)

```bash
curl -X POST http://localhost:8000/cache/clear
```

**ผลลัพธ์:**
```json
{
  "status": "success",
  "message": "All caches cleared"
}
```

## 📊 ดู Logs

```bash
# ดู logs แบบ real-time
tail -f app.log

# หรือ grep เฉพาะ cache
tail -f app.log | grep -i cache
```

**จะเห็น:**
```
2024-11-18 10:30:45 - main - INFO - ✓ Cache hit: abc123...
2024-11-18 10:30:46 - main - INFO - ✓ Cache set: def456...
2024-11-18 10:35:00 - main - INFO - Cache cleanup: removed 10 old entries
```

## 🎯 Next Steps

1. **ทดสอบเสร็จแล้ว?** → Deploy ไป Production
   - ดู `docs/DEPLOYMENT_PRODUCTION.md`

2. **ต้องการ optimize เพิ่ม?** → ดู recommendations
   - ดู `PERFORMANCE_IMPROVEMENTS.md`

3. **พบปัญหา?** → Troubleshooting
   - ดู `tests/LOAD_TESTING.md`

## 🆘 Quick Troubleshooting

### ปัญหา: Server ไม่ start

```bash
# ตรวจสอบ port ว่าถูกใช้หรือไม่
# Linux/Mac
lsof -i :8000

# Windows
netstat -ano | findstr :8000

# แก้ไข: เปลี่ยน port
PORT=8001 python app/main.py
```

### ปัญหา: slowapi not found

```bash
pip install slowapi==0.1.9
```

### ปัญหา: Rate limiting ไม่ทำงาน

```bash
# ตรวจสอบว่าติดตั้งแล้ว
pip list | grep slowapi

# ถ้าไม่มี
pip install slowapi==0.1.9

# Restart server
```

### ปัญหา: Cache ไม่ทำงาน

```bash
# ตรวจสอบ cache stats
curl http://localhost:8000/cache/stats

# ถ้า cache_stats ทั้งหมดเป็น 0
# แสดงว่ายังไม่มี requests เข้ามา
# ลองส่ง request ดู
```

## 📞 Need Help?

1. **ดู Documentation:**
   - `PERFORMANCE_IMPROVEMENTS.md` - สรุปการปรับปรุง
   - `tests/LOAD_TESTING.md` - คู่มือ load testing
   - `docs/DEPLOYMENT_PRODUCTION.md` - คู่มือ deploy

2. **ตรวจสอบ:**
   - Health: `curl http://localhost:8000/health`
   - Cache: `curl http://localhost:8000/cache/stats`
   - Logs: `tail -f app.log`

---

**เวลาที่ใช้:** ~5 นาที  
**ความยาก:** ⭐⭐☆☆☆ (ง่าย)  
**Status:** Ready to Test ✅
