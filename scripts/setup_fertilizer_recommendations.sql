-- ============================================================================
-- Setup: mahbin_npk table
-- คำแนะนำสูตรปุ๋ยสำหรับพืชแต่ละชนิด/ระยะการเจริญเติบโต
-- ============================================================================

-- 1. Create table
CREATE TABLE IF NOT EXISTS mahbin_npk (
    id bigserial PRIMARY KEY,
    crop text NOT NULL,                -- พืช (e.g. นาข้าว, ข้าวโพด)
    growth_stage text NOT NULL,        -- ระยะพืช (e.g. เร่งต้น / แตกกอ)
    fertilizer_formula text NOT NULL,  -- สูตรปุ๋ย NPK (e.g. 46-0-0)
    usage_rate text,                   -- อัตราการใช้ (e.g. 25-30 กก./ไร่)
    primary_nutrients text,            -- ธาตุหลัก/ธาตุรอง (e.g. N P K Mg S)
    benefits text,                     -- ประโยชน์ (e.g. เขียวทน ต้นแข็งแรง)
    embedding vector(1536),            -- สำหรับ vector search
    search_vector tsvector,            -- สำหรับ keyword search
    created_at timestamptz DEFAULT now()
);

-- 2. Auto-update search_vector trigger
CREATE OR REPLACE FUNCTION update_mahbin_npk_search_vector()
RETURNS trigger AS $$
BEGIN
    NEW.search_vector := to_tsvector('simple',
        coalesce(NEW.crop, '') || ' ' ||
        coalesce(NEW.growth_stage, '') || ' ' ||
        coalesce(NEW.fertilizer_formula, '') || ' ' ||
        coalesce(NEW.primary_nutrients, '') || ' ' ||
        coalesce(NEW.benefits, '')
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_mahbin_npk_search_vector ON mahbin_npk;
CREATE TRIGGER trg_mahbin_npk_search_vector
    BEFORE INSERT OR UPDATE ON mahbin_npk
    FOR EACH ROW
    EXECUTE FUNCTION update_mahbin_npk_search_vector();

-- 3. Indexes
CREATE INDEX IF NOT EXISTS idx_mahbin_npk_search_vector
    ON mahbin_npk USING GIN (search_vector);

CREATE INDEX IF NOT EXISTS idx_mahbin_npk_crop
    ON mahbin_npk (crop);

-- 4. Grant permissions
GRANT SELECT ON mahbin_npk TO authenticated;
GRANT SELECT ON mahbin_npk TO anon;

-- 5. Enable RLS (allow read for all)
ALTER TABLE mahbin_npk ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow public read access"
    ON mahbin_npk
    FOR SELECT
    USING (true);
