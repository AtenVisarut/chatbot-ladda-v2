-- =============================================================================
-- admin_templates — Pre-written reply templates for admins to use during handoff
-- =============================================================================
-- Admin สามารถเลือก template แล้วแก้ไข/ส่งให้ user ได้โดยไม่ต้องพิมพ์ใหม่ทุกครั้ง
-- Templates can include placeholders: {product_name}, {plant}, {crop}, {user_name}
-- Admin panel replaces them with actual values before send.
-- =============================================================================

CREATE TABLE IF NOT EXISTS admin_templates (
    id           BIGSERIAL PRIMARY KEY,
    title        TEXT         NOT NULL,
    category     TEXT         NOT NULL DEFAULT 'general',
    content      TEXT         NOT NULL,
    placeholders TEXT[]       NOT NULL DEFAULT '{}',
    usage_count  INTEGER      NOT NULL DEFAULT 0,
    created_by   TEXT,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admin_templates_category
    ON admin_templates (category);
CREATE INDEX IF NOT EXISTS idx_admin_templates_usage
    ON admin_templates (usage_count DESC);

-- updated_at trigger
CREATE OR REPLACE FUNCTION _update_admin_templates_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_admin_templates_updated_at ON admin_templates;
CREATE TRIGGER trg_admin_templates_updated_at
    BEFORE UPDATE ON admin_templates
    FOR EACH ROW
    EXECUTE FUNCTION _update_admin_templates_updated_at();

-- =============================================================================
-- Seed default templates ที่ admin น่าจะใช้บ่อย
-- =============================================================================

INSERT INTO admin_templates (title, category, content, placeholders) VALUES
(
    'ขอบคุณที่รอ + ส่งข้อมูลที่ถูกต้อง',
    'handoff',
    'ขออภัยในความล่าช้าค่ะ ขอตอบคำถาม {product_name} ให้คุณลูกค้าดังนี้ค่ะ

{custom_answer}

หากต้องการข้อมูลเพิ่มเติม สอบถามได้เลยนะคะ 😊',
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
    'สำหรับ {product_name} ใช้กับ{plant}:
• อัตราใช้: {rate}
• วิธีใช้: {how_to_use}
• ช่วงใช้: {when}

กรุณาอ่านฉลากก่อนใช้ทุกครั้งนะคะ 😊',
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
