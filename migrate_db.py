"""
Database Migration: Add enable_monthly_report column
Run this script once after deploying the updated code
"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("❌ DATABASE_URL not set. Exiting.")
    exit(1)

print("🔄 Starting migration...")

try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    # Add enable_monthly_report column if it doesn't exist
    cur.execute("""
        ALTER TABLE chat_mappings 
        ADD COLUMN IF NOT EXISTS enable_monthly_report BOOLEAN DEFAULT TRUE;
    """)
    
    conn.commit()
    print("✅ Migration complete! enable_monthly_report column added.")
    
    cur.close()
    conn.close()
    
except Exception as e:
    print(f"❌ Migration failed: {e}")
    exit(1)