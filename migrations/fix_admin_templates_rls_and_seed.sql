-- =============================================================================
-- แก้ปัญหา: table admin_templates มี RLS แต่ยังไม่มี policy → insert ไม่ได้
-- + seed default templates
-- =============================================================================
-- รันใน Supabase SQL Editor (one-shot)
-- =============================================================================

-- Option 1 (recommended สำหรับ admin table): disable RLS
-- เพราะ Dashboard จะเข้าผ่าน backend API (/api/admin/templates) ที่มี auth อยู่แล้ว
-- และไม่ต้องการให้ anonymous ดูได้
ALTER TABLE admin_templates DISABLE ROW LEVEL SECURITY;

-- Alternatively: keep RLS on but allow authenticated + service_role
-- (ใช้ถ้า Dashboard อ่านด้วย anon key โดยตรง)
-- ALTER TABLE admin_templates ENABLE ROW LEVEL SECURITY;
-- DROP POLICY IF EXISTS admin_templates_anon_read  ON admin_templates;
-- DROP POLICY IF EXISTS admin_templates_auth_all   ON admin_templates;
-- CREATE POLICY admin_templates_anon_read ON admin_templates
--     FOR SELECT TO anon, authenticated USING (true);
-- CREATE POLICY admin_templates_auth_all ON admin_templates
--     FOR ALL TO authenticated USING (true) WITH CHECK (true);

-- =============================================================================
-- Seed defaults
-- =============================================================================

INSERT INTO admin_templates (title, category, content, placeholders) VALUES
(
    'ขอบคุณที่รอ + ส่งข้อมูลที่ถูกต้อง',
    'handoff',
    E'ขออภัยในความล่าช้าค่ะ ขอตอบคำถาม {product_name} ให้คุณลูกค้าดังนี้ค่ะ\n\n{custom_answer}\n\nหากต้องการข้อมูลเพิ่มเติม สอบถามได้เลยนะคะ 😊',
    ARRAY['product_name','custom_answer']
),
(
    'ไม่มีข้อมูลสินค้านี้ในระบบ',
    'handoff',
    'ขออภัยค่ะ น้องลัดดายังไม่มีข้อมูลของ "{product_name}" ในระบบ กรุณาติดต่อเจ้าหน้าที่ ไอ ซี พี ลัดดา โดยตรงค่ะ 🙏',
    ARRAY['product_name']
),
(
    'ปรึกษาเจ้าหน้าที่โดยตรง',
    'handoff',
    'สำหรับคำถามนี้ แนะนำให้ปรึกษาเจ้าหน้าที่ ไอ ซี พี ลัดดา โดยตรงเพื่อคำแนะนำที่เหมาะสมกับสภาพพืชของคุณลูกค้านะคะ 🙏',
    ARRAY[]::TEXT[]
),
(
    'อัตราการใช้ทั่วไป (กรอกเอง)',
    'usage',
    E'สำหรับ {product_name} ใช้กับ{plant}:\n• อัตราใช้: {rate}\n• วิธีใช้: {how_to_use}\n• ช่วงใช้: {when}\n\nกรุณาอ่านฉลากก่อนใช้ทุกครั้งนะคะ 😊',
    ARRAY['product_name','plant','rate','how_to_use','when']
),
(
    'ขอบคุณที่สอบถาม',
    'general',
    'ขอบคุณที่สอบถาม น้องลัดดายินดีให้บริการค่ะ ถ้ามีคำถามเพิ่มเติมสามารถสอบถามได้ตลอดนะคะ 😊',
    ARRAY[]::TEXT[]
),
(
    'คำนวณอัตราการใช้ (Handoff)',
    'handoff',
    'สำหรับการคำนวณอัตราการใช้ให้ตรงกับพื้นที่ของคุณลูกค้า แนะนำให้ปรึกษาเจ้าหน้าที่ ไอ ซี พี ลัดดา โดยตรงค่ะ 🙏',
    ARRAY[]::TEXT[]
),
(
    'สอบถามราคาสินค้า',
    'handoff',
    'สำหรับข้อมูลราคา กรุณาติดต่อสอบถามจากเจ้าหน้าที่ ไอ ซี พี ลัดดา หรือตัวแทนจำหน่ายในพื้นที่โดยตรงค่ะ 🙏',
    ARRAY[]::TEXT[]
)
ON CONFLICT DO NOTHING;

-- ตรวจสอบ
SELECT id, category, title, array_length(placeholders, 1) AS placeholder_count
FROM admin_templates ORDER BY id;
