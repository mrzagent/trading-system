import json
import sys
sys.path.insert(0, 'D:/dev/trading')
from db import get_conn

conn = get_conn()
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS trading_signals (
    id SERIAL PRIMARY KEY,
    strategy VARCHAR(50) NOT NULL,
    coin VARCHAR(10) NOT NULL,
    action VARCHAR(10) NOT NULL,
    confidence FLOAT NOT NULL,
    reason TEXT,
    meta JSONB,
    generated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
)
""")
conn.commit()
conn.close()
print('Table trading_signals created (if not exists)')
