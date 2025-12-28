"""
Database storage module for ValeoBot
Handles persistent storage of chat mappings using PostgreSQL
"""

import os
import json
import logging
from typing import Dict, Optional, List
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


class DatabaseStorage:
    """PostgreSQL storage for chat mappings."""
    
    def __init__(self):
        self.database_url = os.getenv("DATABASE_URL")
        if not self.database_url:
            raise RuntimeError("DATABASE_URL environment variable not set")
        
        # Initialize database schema
        self._init_schema()
    
    def _get_connection(self):
        """Get database connection."""
        return psycopg2.connect(self.database_url, cursor_factory=RealDictCursor)
    
    def _init_schema(self):
        """Create tables if they don't exist."""
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    # Create chat_mappings table
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS chat_mappings (
                            chat_id VARCHAR(255) PRIMARY KEY,
                            chat_type VARCHAR(50) NOT NULL,
                            enable_daily_report BOOLEAN DEFAULT TRUE,
                            enable_weekly_report BOOLEAN DEFAULT TRUE,
                            enable_monthly_report BOOLEAN DEFAULT TRUE,
                            enable_whale_alerts BOOLEAN DEFAULT TRUE,
                            enable_chatter_report BOOLEAN DEFAULT FALSE,
                            whale_alert_threshold INTEGER DEFAULT 4,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    
                    # Create models table (linked models for each chat)
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS chat_models (
                            id SERIAL PRIMARY KEY,
                            chat_id VARCHAR(255) NOT NULL,
                            platform VARCHAR(50) NOT NULL,
                            platform_account_id VARCHAR(255) NOT NULL,
                            nickname VARCHAR(255),
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY (chat_id) REFERENCES chat_mappings(chat_id) ON DELETE CASCADE,
                            UNIQUE(chat_id, platform, platform_account_id)
                        )
                    """)
                    
                    conn.commit()
                    logger.info("Database schema initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database schema: {e}")
            raise
    
    def save_mapping(self, chat_id: str, mapping: dict):
        """
        Save or update chat mapping.
        
        Args:
            chat_id: Telegram chat ID
            mapping: ChatMapping dictionary with models list
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    # Upsert chat_mappings
                    cur.execute("""
                        INSERT INTO chat_mappings 
                        (chat_id, chat_type, enable_daily_report, enable_weekly_report, enable_monthly_report,
                         enable_whale_alerts, enable_chatter_report, whale_alert_threshold, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (chat_id) 
                        DO UPDATE SET
                            chat_type = EXCLUDED.chat_type,
                            enable_daily_report = EXCLUDED.enable_daily_report,
                            enable_weekly_report = EXCLUDED.enable_weekly_report,
                            enable_monthly_report = EXCLUDED.enable_monthly_report,
                            enable_whale_alerts = EXCLUDED.enable_whale_alerts,
                            enable_chatter_report = EXCLUDED.enable_chatter_report,
                            whale_alert_threshold = EXCLUDED.whale_alert_threshold,
                            updated_at = CURRENT_TIMESTAMP
                    """, (
                        chat_id,
                        mapping.get('chat_type', 'agency'),
                        mapping.get('enable_daily_report', True),
                        mapping.get('enable_weekly_report', True),
                        mapping.get('enable_monthly_report', True),
                        mapping.get('enable_whale_alerts', True),
                        mapping.get('enable_chatter_report', False),
                        mapping.get('whale_alert_threshold', 4)
                    ))
                    
                    # Delete existing models for this chat
                    cur.execute("DELETE FROM chat_models WHERE chat_id = %s", (chat_id,))
                    
                    # Insert models
                    for model in mapping.get('models', []):
                        cur.execute("""
                            INSERT INTO chat_models 
                            (chat_id, platform, platform_account_id, nickname)
                            VALUES (%s, %s, %s, %s)
                        """, (
                            chat_id,
                            model.get('platform'),
                            model.get('platform_account_id'),
                            model.get('nickname')
                        ))
                    
                    conn.commit()
                    logger.info(f"Saved mapping for chat {chat_id}")
        except Exception as e:
            logger.error(f"Failed to save mapping for chat {chat_id}: {e}")
            raise
    
    def load_mapping(self, chat_id: str) -> Optional[dict]:
        """
        Load chat mapping from database.
        
        Args:
            chat_id: Telegram chat ID
        
        Returns:
            ChatMapping dictionary or None if not found
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    # Get chat mapping
                    cur.execute("""
                        SELECT * FROM chat_mappings WHERE chat_id = %s
                    """, (chat_id,))
                    
                    mapping = cur.fetchone()
                    if not mapping:
                        return None
                    
                    # Get models
                    cur.execute("""
                        SELECT platform, platform_account_id, nickname
                        FROM chat_models
                        WHERE chat_id = %s
                        ORDER BY id
                    """, (chat_id,))
                    
                    models = cur.fetchall()
                    
                    return {
                        'chat_type': mapping['chat_type'],
                        'enable_daily_report': mapping['enable_daily_report'],
                        'enable_weekly_report': mapping['enable_weekly_report'],
                        'enable_monthly_report': mapping.get('enable_monthly_report', True),
                        'enable_whale_alerts': mapping['enable_whale_alerts'],
                        'enable_chatter_report': mapping['enable_chatter_report'],
                        'whale_alert_threshold': mapping['whale_alert_threshold'],
                        'models': [dict(model) for model in models]
                    }
        except Exception as e:
            logger.error(f"Failed to load mapping for chat {chat_id}: {e}")
            return None
    
    def load_all_mappings(self) -> Dict[str, dict]:
        """
        Load all chat mappings from database.
        
        Returns:
            Dictionary of chat_id -> ChatMapping
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    # Get all chat mappings
                    cur.execute("SELECT chat_id FROM chat_mappings")
                    chat_ids = [row['chat_id'] for row in cur.fetchall()]
                    
                    mappings = {}
                    for chat_id in chat_ids:
                        mapping = self.load_mapping(chat_id)
                        if mapping:
                            mappings[chat_id] = mapping
                    
                    logger.info(f"Loaded {len(mappings)} chat mappings from database")
                    return mappings
        except Exception as e:
            logger.error(f"Failed to load all mappings: {e}")
            return {}
    
    def delete_mapping(self, chat_id: str):
        """
        Delete chat mapping from database.
        
        Args:
            chat_id: Telegram chat ID
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM chat_mappings WHERE chat_id = %s", (chat_id,))
                    conn.commit()
                    logger.info(f"Deleted mapping for chat {chat_id}")
        except Exception as e:
            logger.error(f"Failed to delete mapping for chat {chat_id}: {e}")
            raise