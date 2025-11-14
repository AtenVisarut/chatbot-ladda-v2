-- Create conversation_memory table for storing chat history
-- This table stores user conversations for context and memory

CREATE TABLE IF NOT EXISTS conversation_memory (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_conversation_memory_user_id 
ON conversation_memory(user_id);

CREATE INDEX IF NOT EXISTS idx_conversation_memory_created_at 
ON conversation_memory(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_conversation_memory_user_created 
ON conversation_memory(user_id, created_at DESC);

-- Enable Row Level Security (optional)
ALTER TABLE conversation_memory ENABLE ROW LEVEL SECURITY;

-- Create policy to allow all operations (adjust based on your needs)
CREATE POLICY "Allow all operations on conversation_memory" 
ON conversation_memory 
FOR ALL 
USING (true) 
WITH CHECK (true);

-- Grant permissions
GRANT ALL ON conversation_memory TO authenticated;
GRANT ALL ON conversation_memory TO anon;
GRANT USAGE, SELECT ON SEQUENCE conversation_memory_id_seq TO authenticated;
GRANT USAGE, SELECT ON SEQUENCE conversation_memory_id_seq TO anon;

-- Function to clean old messages (keep last 30 days)
CREATE OR REPLACE FUNCTION cleanup_old_conversations()
RETURNS void AS $$
BEGIN
    DELETE FROM conversation_memory
    WHERE created_at < NOW() - INTERVAL '30 days';
END;
$$ LANGUAGE plpgsql;

-- Optional: Create a scheduled job to run cleanup (requires pg_cron extension)
-- SELECT cron.schedule('cleanup-conversations', '0 2 * * *', 'SELECT cleanup_old_conversations()');

COMMENT ON TABLE conversation_memory IS 'Stores conversation history for chatbot memory and context';
COMMENT ON COLUMN conversation_memory.user_id IS 'LINE user ID';
COMMENT ON COLUMN conversation_memory.role IS 'Message role: user or assistant';
COMMENT ON COLUMN conversation_memory.content IS 'Message content';
COMMENT ON COLUMN conversation_memory.metadata IS 'Additional metadata (e.g., message_type, confidence)';
