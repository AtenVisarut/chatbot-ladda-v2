-- Setup Vector Search for Knowledge Table with E5 Embeddings (768 dimensions)
-- Run this in Supabase SQL Editor

-- 1. Check current embedding dimensions
SELECT 
    pg_typeof(embedding) as embedding_type,
    COUNT(*) as total_records
FROM knowledge
WHERE embedding IS NOT NULL
LIMIT 1;

-- 2. Drop old index if exists
DROP INDEX IF EXISTS idx_knowledge_embedding;

-- 3. Create new vector index for 768-dimensional embeddings
CREATE INDEX idx_knowledge_embedding ON knowledge 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- 4. Drop old RPC function if exists
DROP FUNCTION IF EXISTS match_knowledge(vector, float, int);

-- 5. Create new RPC function for 768-dimensional vectors
CREATE OR REPLACE FUNCTION match_knowledge(
  query_embedding vector(768),
  match_threshold float DEFAULT 0.5,
  match_count int DEFAULT 5
)
RETURNS TABLE (
  id bigint,
  content text,
  similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    knowledge.id,
    knowledge.content,
    1 - (knowledge.embedding <=> query_embedding) AS similarity
  FROM knowledge
  WHERE knowledge.embedding IS NOT NULL
    AND 1 - (knowledge.embedding <=> query_embedding) > match_threshold
  ORDER BY knowledge.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- 6. Verify setup
SELECT 
    'Knowledge search ready (E5, 768 dim)!' as status,
    COUNT(*) as total_knowledge,
    COUNT(embedding) as knowledge_with_embeddings
FROM knowledge;

-- 7. Test the function (optional)
-- SELECT * FROM match_knowledge(
--     array_fill(0, ARRAY[768])::vector,
--     0.3,
--     3
-- );
