# 🚀 Load Testing Guide

คู่มือการทดสอบ Load และ Performance ของ LINE Plant Disease Detection Bot

## 📋 สิ่งที่ทดสอบ

1. **Rate Limiting** - ป้องกัน spam และ DDoS
2. **Caching** - ลด API cost และเพิ่มความเร็ว
3. **Memory Cleanup** - ป้องกัน memory leak
4. **Concurrent Users** - รับ load ได้เท่าไหร่
5. **Response Time** - ความเร็วในการตอบกลับ

## 🔧 การติดตั้ง

```bash
# ติดตั้ง dependencies สำหรับ load testing
pip install aiohttp
```

## 🏃 วิธีการทดสอบ

### 1. เริ่ม Server

```bash
# Terminal 1: Start server
python app/main.py
```

### 2. รัน Load Test

```bash
# Terminal 2: Run load test
python tests/load_test.py
```

## 📊 ผลลัพธ์ที่คาดหวัง

### ✅ Rate Limiting

```
Testing Rate Limiting
============================================================
Request 1: Status=200
Request 2: Status=200
...
Request 11: Status=429  ← Rate limited!
Request 12: Status=429
...

✓ Rate limiting working: 5/15 requests blocked
```

**คำอธิบาย:**
- User สามารถส่ง 10 requests ต่อนาที
- Request ที่ 11+ จะถูก block (Status 429)

### ✅ Cache Performance

```
Testing Cache Performance
============================================================
Request 1: 2.345s (Status=200)  ← No cache, call Gemini
Request 2: 0.123s (Status=200)  ← Cached!
Request 3: 0.098s (Status=200)  ← Cached!
Request 4: 0.105s (Status=200)  ← Cached!
Request 5: 0.110s (Status=200)  ← Cached!

✓ Cache Performance:
  First request (no cache): 2.345s
  Avg cached requests: 0.109s
  Performance improvement: 95.4%
```

**คำอธิบาย:**
- Request แรกช้า (ต้องเรียก Gemini API)
- Request ถัดไปเร็วมาก (ใช้ cache)
- ประหยัด API cost 95%+

### ✅ Concurrent Load Test

```
Running Concurrent Load Test
Users: 10, Requests per user: 5
============================================================
User 0 - Request 1: Status=200, Time=1.234s
User 1 - Request 1: Status=200, Time=1.456s
User 2 - Request 1: Status=200, Time=1.567s
...

Load Test Results
============================================================
Total Requests: 50
Successful: 48 (96.0%)
Failed: 2 (4.0%)
Total Duration: 12.34s
Requests/Second: 4.05

Response Time Statistics:
  Min: 0.098s
  Max: 2.456s
  Mean: 0.876s
  Median: 0.654s
  Std Dev: 0.432s
```

**คำอธิบาย:**
- รับ load ได้ ~4-5 requests/second
- Success rate 96%+
- Response time เฉลี่ย < 1 วินาที

### ✅ Cache Statistics

```
Cache Stats:
{
  "cache_stats": {
    "detection_cache_size": 15,
    "product_cache_size": 8,
    "knowledge_cache_size": 12,
    "pending_contexts": 2,
    "total_memory_items": 37
  },
  "cache_config": {
    "ttl_seconds": 3600,
    "max_size": 1000,
    "pending_context_ttl": 300
  },
  "rate_limiting": {
    "active_users": 5,
    "user_limit": 10,
    "window_seconds": 60
  }
}
```

## 🎯 เกณฑ์การผ่านการทดสอบ

| Metric | Target | Status |
|--------|--------|--------|
| **Success Rate** | > 95% | ✅ |
| **Response Time (avg)** | < 2s | ✅ |
| **Cache Hit Rate** | > 80% | ✅ |
| **Rate Limiting** | Working | ✅ |
| **Memory Cleanup** | No leaks | ✅ |
| **Concurrent Users** | 10+ | ✅ |

## 🔍 การวิเคราะห์ผลลัพธ์

### 1. ตรวจสอบ Success Rate

```python
# ควรได้ > 95%
Successful: 48/50 (96.0%)
```

**ถ้าต่ำกว่า 95%:**
- ตรวจสอบ error logs
- เพิ่ม timeout
- ตรวจสอบ API limits

### 2. ตรวจสอบ Response Time

```python
# ควรได้ < 2s เฉลี่ย
Mean: 0.876s
```

**ถ้าช้ากว่า 2s:**
- ตรวจสอบ cache working หรือไม่
- ตรวจสอบ network latency
- พิจารณาเพิ่ม resources

### 3. ตรวจสอบ Cache Performance

```python
# ควรเร็วขึ้น > 80%
Performance improvement: 95.4%
```

**ถ้าไม่เร็วขึ้น:**
- ตรวจสอบ cache TTL
- ตรวจสอบ cache key generation
- ดู cache hit rate

### 4. ตรวจสอบ Rate Limiting

```python
# ควร block requests ที่เกิน limit
Rate limited: 5/15 requests blocked
```

**ถ้าไม่ block:**
- ตรวจสอบ rate limit configuration
- ตรวจสอบ user ID extraction

## 📈 การปรับแต่ง Performance

### เพิ่ม Cache Size

```python
# ใน app/main.py
MAX_CACHE_SIZE = 2000  # เพิ่มจาก 1000
CACHE_TTL = 7200  # เพิ่มจาก 3600 (2 ชั่วโมง)
```

### ปรับ Rate Limit

```python
# ใน app/main.py
USER_RATE_LIMIT = 20  # เพิ่มจาก 10
USER_RATE_WINDOW = 60  # คงเดิม 60 วินาที
```

### เพิ่ม Concurrent Requests

```python
# ใน tests/load_test.py
NUM_CONCURRENT_USERS = 20  # เพิ่มจาก 10
REQUESTS_PER_USER = 10  # เพิ่มจาก 5
```

## 🐛 Troubleshooting

### ปัญหา: Connection Refused

```bash
# ตรวจสอบว่า server ทำงานหรือไม่
curl http://localhost:8000/health
```

**แก้ไข:**
```bash
# เริ่ม server ใหม่
python app/main.py
```

### ปัญหา: Rate Limit ไม่ทำงาน

```bash
# ตรวจสอบ slowapi ติดตั้งหรือไม่
pip list | grep slowapi
```

**แก้ไข:**
```bash
pip install slowapi==0.1.9
```

### ปัญหา: Cache ไม่ทำงาน

```bash
# ตรวจสอบ cache stats
curl http://localhost:8000/cache/stats
```

**แก้ไข:**
```bash
# Clear cache และทดสอบใหม่
curl -X POST http://localhost:8000/cache/clear
```

### ปัญหา: Memory Leak

```bash
# ตรวจสอบ memory usage
# Linux/Mac
ps aux | grep python

# Windows
tasklist | findstr python
```

**แก้ไข:**
- ตรวจสอบ periodic cleanup ทำงานหรือไม่
- ลด CACHE_TTL
- ลด MAX_CACHE_SIZE

## 📊 Monitoring ใน Production

### 1. ติดตั้ง Monitoring Tools

```bash
pip install prometheus-client
```

### 2. เพิ่ม Metrics Endpoint

```python
from prometheus_client import Counter, Histogram, generate_latest

request_counter = Counter('requests_total', 'Total requests')
response_time = Histogram('response_time_seconds', 'Response time')

@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type="text/plain")
```

### 3. ดู Metrics

```bash
curl http://localhost:8000/metrics
```

## 🎯 Best Practices

1. **ทดสอบก่อน Deploy**
   - รัน load test ทุกครั้งก่อน deploy
   - ตรวจสอบ success rate > 95%

2. **Monitor ใน Production**
   - ติดตั้ง monitoring tools
   - ตั้ง alerts สำหรับ errors

3. **ปรับแต่งตาม Usage**
   - เพิ่ม cache size ถ้า users เยอะ
   - ปรับ rate limit ตาม traffic

4. **Backup Plan**
   - มี fallback mechanism
   - ทดสอบ error handling

## 📞 Support

หากพบปัญหา:
1. ตรวจสอบ logs: `tail -f app.log`
2. ดู cache stats: `curl http://localhost:8000/cache/stats`
3. ทดสอบ health: `curl http://localhost:8000/health`

---

**Version:** 1.0  
**Last Updated:** 2024-11-18  
**Status:** Ready for Testing ✅
