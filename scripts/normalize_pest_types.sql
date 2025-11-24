-- Normalize Pest Types in Analytics Events
-- แก้ไขข้อมูลที่ซ้ำซ้อนให้เป็นมาตรฐานเดียวกัน

-- 1. รวม "เชื้อรา (Fungus)" เป็น "เชื้อรา"
UPDATE analytics_events
SET pest_type = 'เชื้อรา'
WHERE pest_type IN ('เชื้อรา (Fungus)', 'Fungus', 'fungus');

-- 2. รวม "ศัตรูพืช (Pest)" เป็น "แมลง"
UPDATE analytics_events
SET pest_type = 'แมลง'
WHERE pest_type IN ('ศัตรูพืช', 'Pest', 'pest', 'ศัตรูพืช (Pest)');

-- 3. รวม "ไวรัส (Virus)" เป็น "ไวรัส"
UPDATE analytics_events
SET pest_type = 'ไวรัส'
WHERE pest_type IN ('ไวรัส (Virus)', 'Virus', 'virus');

-- 4. รวม "วัชพืช (Weed)" เป็น "วัชพืช"
UPDATE analytics_events
SET pest_type = 'วัชพืช'
WHERE pest_type IN ('วัชพืช (Weed)', 'Weed', 'weed');

-- 5. ตรวจสอบผลลัพธ์
SELECT pest_type, COUNT(*) as count
FROM analytics_events
WHERE event_type = 'image_analysis'
  AND pest_type IS NOT NULL
GROUP BY pest_type
ORDER BY count DESC;

-- 6. แสดงข้อมูลที่อัปเดต
SELECT 
    'Total updated' as status,
    COUNT(*) as count
FROM analytics_events
WHERE pest_type IN ('เชื้อรา', 'แมลง', 'ไวรัส', 'วัชพืช');
