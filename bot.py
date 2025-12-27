"""
ValeoBot - OnlyMonster Telegram Statistics Bot
A professional Telegram bot for tracking OnlyFans revenue through OnlyMonster API.
"""

import os
import json
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass

import requests
from dotenv import load_dotenv
from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackContext,
)

# Import chatter tracker module
from chatter_tracker import ChatterPerformanceClient, format_chatter_report

# Import database storage
from db_storage import DatabaseStorage

# ============================================================================
# Configuration & Setup
# ============================================================================

load_dotenv()

# Environment variables
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
OM_API_TOKEN = os.getenv("OM_API_TOKEN")
OM_BASE_URL = os.getenv("OM_BASE_URL", "https://omapi.onlymonster.ai")

if not TG_BOT_TOKEN or not OM_API_TOKEN:
    raise RuntimeError(
        "Missing required environment variables: TG_BOT_TOKEN and OM_API_TOKEN must be set"
    )

# Timezone for OnlyFans day calculation (1 AM - 1 AM Berlin time)
BERLIN_TZ = ZoneInfo("Europe/Berlin")

# File storage
MAPPING_FILE = "chat_mapping.json"

# Logging configuration
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ============================================================================
# Data Models
# ============================================================================


@dataclass
class ModelConfig:
    """Configuration for a single model."""
    platform: str
    platform_account_id: str
    nickname: Optional[str] = None  # Friendly display name


@dataclass
class ChatMapping:
    """Represents a chat's connection to platform accounts."""
    models: list  # List of ModelConfig objects
    chat_type: str = "agency"  # "agency" or "chatter"
    enable_daily_report: bool = True
    enable_weekly_report: bool = True
    enable_whale_alerts: bool = True
    enable_chatter_report: bool = False  # New: Enable daily chatter performance report
    whale_alert_threshold: int = 4  # Buying power score threshold (0-5)


@dataclass
class RevenueStats:
    """Revenue statistics for a time period."""
    total_amount: float
    currency: str
    transaction_count: int
    start_time: datetime
    end_time: datetime
    new_subscribers: Optional[int] = None
    total_subscribers: Optional[int] = None


# ============================================================================
# Storage Management
# ============================================================================


class StorageManager:
    """Manages persistent storage of chat-to-model mappings."""
    
    def __init__(self, filepath: str):
        self.filepath = filepath
    
    def load(self) -> Dict[str, ChatMapping]:
        """Load mappings from file."""
        if not os.path.exists(self.filepath):
            return {}
        
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                mappings = {}
                for chat_id, mapping_data in data.items():
                    # Handle old format (backwards compatibility)
                    if "platform" in mapping_data and "platform_account_id" in mapping_data:
                        # Old single-model format - convert to new format
                        models = [ModelConfig(
                            platform=mapping_data["platform"],
                            platform_account_id=mapping_data["platform_account_id"],
                            nickname=None
                        )]
                    else:
                        # New multi-model format
                        models = [
                            ModelConfig(
                                platform=model_data["platform"],
                                platform_account_id=model_data["platform_account_id"],
                                nickname=model_data.get("nickname")
                            )
                            for model_data in mapping_data.get("models", [])
                        ]
                    
                    # Set defaults for missing fields
                    if "chat_type" not in mapping_data:
                        mapping_data["chat_type"] = "agency"
                        mapping_data["enable_daily_report"] = True
                        mapping_data["enable_weekly_report"] = True
                        mapping_data["enable_whale_alerts"] = True
                        mapping_data["enable_chatter_report"] = False
                        mapping_data["whale_alert_threshold"] = 4
                    
                    # Add chatter_report field if missing (backwards compatibility)
                    if "enable_chatter_report" not in mapping_data:
                        mapping_data["enable_chatter_report"] = False
                    
                    mappings[chat_id] = ChatMapping(
                        models=models,
                        chat_type=mapping_data.get("chat_type", "agency"),
                        enable_daily_report=mapping_data.get("enable_daily_report", True),
                        enable_weekly_report=mapping_data.get("enable_weekly_report", True),
                        enable_whale_alerts=mapping_data.get("enable_whale_alerts", True),
                        enable_chatter_report=mapping_data.get("enable_chatter_report", False),
                        whale_alert_threshold=mapping_data.get("whale_alert_threshold", 4),
                    )
                return mappings
        except Exception as e:
            logger.error(f"Failed to load mappings: {e}")
            return {}
    
    def save(self, mappings: Dict[str, ChatMapping]) -> None:
        """Save mappings to file."""
        try:
            data = {
                chat_id: {
                    "models": [
                        {
                            "platform": model.platform,
                            "platform_account_id": model.platform_account_id,
                            "nickname": model.nickname,
                        }
                        for model in mapping.models
                    ],
                    "chat_type": mapping.chat_type,
                    "enable_daily_report": mapping.enable_daily_report,
                    "enable_weekly_report": mapping.enable_weekly_report,
                    "enable_whale_alerts": mapping.enable_whale_alerts,
                    "enable_chatter_report": mapping.enable_chatter_report,
                    "whale_alert_threshold": mapping.whale_alert_threshold,
                }
                for chat_id, mapping in mappings.items()
            }
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save mappings: {e}")


# Initialize storage (use database if DATABASE_URL is available, otherwise use JSON)
try:
    if os.getenv("DATABASE_URL"):
        logger.info("Using PostgreSQL database for storage")
        _db_storage = DatabaseStorage()
        
        # Wrapper to make DatabaseStorage compatible with existing code
        class DatabaseStorageWrapper:
            def load(self) -> Dict[str, ChatMapping]:
                """Load all mappings from database."""
                mappings_dict = _db_storage.load_all_mappings()
                mappings = {}
                for chat_id, mapping_data in mappings_dict.items():
                    # Convert models from dict to ModelConfig objects
                    models = [
                        ModelConfig(
                            platform=m['platform'],
                            platform_account_id=m['platform_account_id'],
                            nickname=m.get('nickname')
                        )
                        for m in mapping_data.get('models', [])
                    ]
                    
                    mappings[chat_id] = ChatMapping(
                        models=models,
                        chat_type=mapping_data.get('chat_type', 'agency'),
                        enable_daily_report=mapping_data.get('enable_daily_report', True),
                        enable_weekly_report=mapping_data.get('enable_weekly_report', True),
                        enable_whale_alerts=mapping_data.get('enable_whale_alerts', True),
                        enable_chatter_report=mapping_data.get('enable_chatter_report', False),
                        whale_alert_threshold=mapping_data.get('whale_alert_threshold', 4),
                    )
                return mappings
            
            def save(self, mappings: Dict[str, ChatMapping]) -> None:
                """Save all mappings to database."""
                # First, get all existing chat_ids from database
                existing_mappings = _db_storage.load_all_mappings()
                existing_chat_ids = set(existing_mappings.keys())
                new_chat_ids = set(mappings.keys())
                
                # Delete chat_ids that are no longer in the mappings dict
                deleted_chat_ids = existing_chat_ids - new_chat_ids
                for chat_id in deleted_chat_ids:
                    _db_storage.delete_mapping(chat_id)
                    logger.info(f"Deleted mapping for chat {chat_id} from database")
                
                # Save or update remaining mappings
                for chat_id, mapping in mappings.items():
                    # Convert ChatMapping to dict
                    mapping_dict = {
                        'chat_type': mapping.chat_type,
                        'enable_daily_report': mapping.enable_daily_report,
                        'enable_weekly_report': mapping.enable_weekly_report,
                        'enable_whale_alerts': mapping.enable_whale_alerts,
                        'enable_chatter_report': mapping.enable_chatter_report,
                        'whale_alert_threshold': mapping.whale_alert_threshold,
                        'models': [
                            {
                                'platform': m.platform,
                                'platform_account_id': m.platform_account_id,
                                'nickname': m.nickname
                            }
                            for m in mapping.models
                        ]
                    }
                    _db_storage.save_mapping(chat_id, mapping_dict)

        
        storage = DatabaseStorageWrapper()
        logger.info("Database storage initialized successfully")
    else:
        logger.info("DATABASE_URL not found, using JSON file storage")
        storage = StorageManager(MAPPING_FILE)
except Exception as e:
    logger.error(f"Failed to initialize database storage, falling back to JSON: {e}")
    storage = StorageManager(MAPPING_FILE)


# ============================================================================
# OnlyMonster API Client
# ============================================================================


class OnlyMonsterClient:
    """Client for interacting with OnlyMonster API."""
    
    def __init__(self, api_token: str, base_url: str):
        self.api_token = api_token
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "x-om-auth-token": api_token,
            "accept": "application/json",
        })
    
    def get_transactions(
        self,
        platform: str,
        account_id: str,
        start: datetime,
        end: datetime,
        limit: int = 500
    ) -> Dict:
        """
        Fetch transactions for a platform account within a time range.
        
        Args:
            platform: Platform name (e.g., 'onlyfans', 'fansly')
            account_id: Platform account ID
            start: Start datetime (UTC)
            end: End datetime (UTC)
            limit: Maximum number of transactions to fetch
        
        Returns:
            API response containing transactions
        """
        url = (
            f"{self.base_url}/api/v0/platforms/{platform.lower()}"
            f"/accounts/{account_id}/transactions"
        )
        
        params = {
            "start": start.isoformat().replace("+00:00", "Z"),
            "end": end.isoformat().replace("+00:00", "Z"),
            "limit": limit,
        }
        
        logger.info(f"Fetching transactions: {url} with params {params}")
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            raise
    
    def get_subscribers(
        self,
        platform: str,
        account_id: str,
        start: datetime,
        end: datetime
    ) -> Dict:
        """
        Fetch subscriber statistics for a platform account.
        
        Args:
            platform: Platform name (e.g., 'onlyfans', 'fansly')
            account_id: Platform account ID
            start: Start datetime (UTC)
            end: End datetime (UTC)
        
        Returns:
            Subscriber data from API
        """
        url = (
            f"{self.base_url}/api/v0/platforms/{platform.lower()}"
            f"/accounts/{account_id}/subscribers"
        )
        
        params = {
            "start": start.isoformat().replace("+00:00", "Z"),
            "end": end.isoformat().replace("+00:00", "Z"),
        }
        
        logger.info(f"Fetching subscribers: {url} with params {params}")
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to fetch subscriber data: {e}")
            return {}
    
    def calculate_revenue(
        self,
        platform: str,
        account_id: str,
        start: datetime,
        end: datetime
    ) -> RevenueStats:
        """
        Calculate total revenue for a time period.
        
        Args:
            platform: Platform name
            account_id: Platform account ID
            start: Start datetime (UTC)
            end: End datetime (UTC)
        
        Returns:
            RevenueStats object with aggregated data
        """
        try:
            data = self.get_transactions(platform, account_id, start, end)
            items = data.get("items", []) or []
            
            total_amount = 0.0
            currency = "USD"  # Default currency
            
            for transaction in items:
                amount = transaction.get("amount")
                if amount is not None:
                    try:
                        total_amount += float(amount)
                    except (TypeError, ValueError) as e:
                        logger.warning(f"Invalid amount value: {amount} - {e}")
                        continue
                
                # Get currency from first transaction
                if currency == "USD" and "currency" in transaction:
                    currency = transaction["currency"]
            
            # Try to get subscriber data
            new_subscribers = None
            total_subscribers = None
            try:
                sub_data = self.get_subscribers(platform, account_id, start, end)
                if sub_data:
                    new_subscribers = sub_data.get("new_subscribers")
                    total_subscribers = sub_data.get("total_subscribers")
            except Exception as e:
                logger.warning(f"Could not fetch subscriber data: {e}")
            
            # Calculate NET revenue (after OnlyFans 20% fee)
            # OnlyFans takes 20%, creator gets 80%
            net_amount = total_amount * 0.80
            
            return RevenueStats(
                total_amount=net_amount,  # Show NET revenue instead of gross
                currency=currency,
                transaction_count=len(items),
                start_time=start,
                end_time=end,
                new_subscribers=new_subscribers,
                total_subscribers=total_subscribers,
            )
        
        except Exception as e:
            logger.error(f"Failed to calculate revenue: {e}")
            raise


om_client = OnlyMonsterClient(OM_API_TOKEN, OM_BASE_URL)


# ============================================================================
# Date/Time Utilities
# ============================================================================


class OnlyFansCalendar:
    """Utilities for OnlyFans day calculations (1 AM - 1 AM Berlin time)."""
    
    @staticmethod
    def get_of_day_range(date) -> Tuple[datetime, datetime]:
        """
        Calculate start/end times for an OnlyFans day.
        
        OnlyFans day runs from 1:00 AM to 12:59:59 AM next day (Berlin time).
        
        Args:
            date: Date object (date, not datetime)
        
        Returns:
            Tuple of (start_utc, end_utc)
        """
        # Start: 1:00 AM Berlin time on the given date
        start_local = datetime(
            date.year, date.month, date.day, 1, 0, 0, 0,
            tzinfo=BERLIN_TZ
        )
        
        # End: 0:59:59.999999 AM next day Berlin time
        end_local = start_local + timedelta(days=1) - timedelta(microseconds=1)
        
        # Convert to UTC
        start_utc = start_local.astimezone(timezone.utc)
        end_utc = end_local.astimezone(timezone.utc)
        
        return start_utc, end_utc
    
    @staticmethod
    def get_current_of_day() -> Tuple[datetime, datetime]:
        """Get start/end times for the current OnlyFans day (1 AM to NOW)."""
        now_berlin = datetime.now(BERLIN_TZ)
        today = now_berlin.date()
        
        # Start: 1:00 AM Berlin time today
        start_local = datetime(
            today.year, today.month, today.day, 1, 0, 0, 0,
            tzinfo=BERLIN_TZ
        )
        
        # If it's currently before 1 AM, we're still in yesterday's OF day
        if now_berlin.hour < 1:
            start_local = start_local - timedelta(days=1)
        
        # End: NOW
        end_local = now_berlin
        
        # Convert to UTC
        start_utc = start_local.astimezone(timezone.utc)
        end_utc = end_local.astimezone(timezone.utc)
        
        return start_utc, end_utc
    
    @staticmethod
    def get_previous_of_day() -> Tuple[datetime, datetime]:
        """Get start/end times for the previous OnlyFans day."""
        today = datetime.now(BERLIN_TZ).date()
        yesterday = today - timedelta(days=1)
        return OnlyFansCalendar.get_of_day_range(yesterday)


# ============================================================================
# Message Formatting
# ============================================================================


class MessageFormatter:
    """Formats bot messages with proper styling."""
    
    @staticmethod
    def format_revenue(
        stats: RevenueStats,
        account_id: str,
        platform: str,
        title: str = "Revenue Report"
    ) -> str:
        """Format revenue statistics as a Telegram message."""
        
        # Format the time range in Berlin timezone
        start_berlin = stats.start_time.astimezone(BERLIN_TZ)
        end_berlin = stats.end_time.astimezone(BERLIN_TZ)
        
        msg = f"📊 *{title}*\n\n"
        msg += f"🎯 Model: `{account_id}`\n"
        msg += f"🌐 Platform: `{platform.title()}`\n\n"
        msg += f"💰 Revenue: *${stats.total_amount:,.2f}*\n"
        
        # Add new subscriber info if available
        if stats.new_subscribers is not None and stats.new_subscribers > 0:
            msg += f"👥 New Subscribers: *{stats.new_subscribers}*\n"
        
        msg += f"\n📅 Period: {start_berlin.strftime('%d.%m.%Y %H:%M')} - {end_berlin.strftime('%d.%m.%Y %H:%M')}\n"
        
        return msg
    
    @staticmethod
    def format_error(error_msg: str) -> str:
        """Format error message."""
        return f"⚠️ *Error*\n\n{error_msg}"
    
    @staticmethod
    def format_success(msg: str) -> str:
        """Format success message."""
        return f"✅ {msg}"


# ============================================================================
# Bot Command Handlers
# ============================================================================


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    welcome_msg = (
        "👋 *Welcome to ValeoBot*\n\n"
        "I help you track OnlyFans revenue through OnlyMonster API.\n\n"
        "📋 *Available Commands:*\n\n"
        "/link `<platform>` `<account_id>` - Link this chat to a model\n"
        "   Example: `/link onlyfans maxes`\n\n"
        "/today - Show today's revenue & new subscribers\n"
        "/yesterday - Show yesterday's stats\n"
        "/week - Show last 7 days summary\n"
        "/unlink - Remove model link from this chat\n"
        "/help - Show this help message\n\n"
        "⏰ *Automatic Reports:*\n"
        "• Daily report at 1:00 AM (yesterday's stats)\n"
        "• Weekly report every Monday at 1:00 AM (last 7 days)\n\n"
        "All times are in Berlin timezone 🇩🇪"
    )
    
    await update.message.reply_text(welcome_msg, parse_mode="Markdown")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    await cmd_start(update, context)


async def cmd_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /link command to connect a chat with a model."""
    chat_id = str(update.effective_chat.id)
    
    # Usage: /link <platform> <account_id> [agency|chatter] [nickname]
    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Invalid usage.\n\n"
            "**Usage:** `/link <platform> <account_id> [type] [nickname]`\n\n"
            "**Examples:**\n"
            "With nickname: `/link onlyfans 454315739 agency YourModel`\n"
            "Without: `/link onlyfans 454315739 agency`\n\n"
            "**Add more models:**\n"
            "`/link onlyfans 123456 agency AnotherModel`\n\n"
            "**Types:**\n"
            "• `agency` - Daily/weekly reports (NO whale alerts)\n"
            "• `chatter` - Whale alerts only (NO reports)\n\n"
            "Supported platforms: onlyfans, fansly",
            parse_mode="Markdown"
        )
        return
    
    platform = context.args[0].strip().lower()
    account_id = context.args[1].strip()
    
    # Parse optional arguments
    chat_type = None
    nickname = None
    
    # Check 3rd and 4th arguments
    if len(context.args) >= 3:
        arg3 = context.args[2].strip().lower()
        if arg3 in ["agency", "chatter"]:
            chat_type = arg3
            # Check if 4th arg is nickname
            if len(context.args) >= 4:
                nickname = " ".join(context.args[3:])  # Allow multi-word nicknames
        else:
            # 3rd arg is nickname, not chat type
            nickname = " ".join(context.args[2:])
    
    # Validate platform
    supported_platforms = ["onlyfans", "fansly"]
    if platform not in supported_platforms:
        await update.message.reply_text(
            f"❌ Unsupported platform: `{platform}`\n\n"
            f"Supported platforms: {', '.join(supported_platforms)}",
            parse_mode="Markdown"
        )
        return
    
    # Load existing mappings
    mappings = storage.load()
    
    # Check if chat already has models
    if chat_id in mappings:
        # Add to existing models
        existing_mapping = mappings[chat_id]
        
        # Check if model already exists
        for model in existing_mapping.models:
            if model.platform == platform and model.platform_account_id == account_id:
                await update.message.reply_text(
                    f"⚠️ Model `{account_id}` on `{platform}` is already linked to this group!",
                    parse_mode="Markdown"
                )
                return
        
        # Add new model
        existing_mapping.models.append(ModelConfig(
            platform=platform,
            platform_account_id=account_id,
            nickname=nickname
        ))
        
        mappings[chat_id] = existing_mapping
        storage.save(mappings)
        
        model_list = ", ".join([
            f"`{m.nickname or m.platform_account_id}`" for m in existing_mapping.models
        ])
        
        display_name = nickname or account_id
        
        await update.message.reply_text(
            f"✅ Added model **{display_name}** (`{account_id}`) on `{platform}`\n\n"
            f"**Linked models:** {model_list}\n\n"
            f"**Configuration ({existing_mapping.chat_type}):**\n"
            f"• Daily reports: {'✅' if existing_mapping.enable_daily_report else '❌'}\n"
            f"• Weekly reports: {'✅' if existing_mapping.enable_weekly_report else '❌'}\n"
            f"• Whale alerts: {'✅' if existing_mapping.enable_whale_alerts else '❌'}\n\n"
            f"Use `/today` for all models or `/today {existing_mapping.models[0].nickname or existing_mapping.models[0].platform_account_id}` for specific model",
            parse_mode="Markdown"
        )
        
    else:
        # First model for this chat
        # Determine chat type and configure defaults
        if chat_type == "agency":
            # Agency: Daily + Weekly reports, NO whale alerts
            enable_daily = True
            enable_weekly = True
            enable_whale = False
        elif chat_type == "chatter":
            # Chatter: Only whale alerts (threshold 4+), NO reports
            enable_daily = False
            enable_weekly = False
            enable_whale = True
        else:
            # Default to agency if not specified
            chat_type = "agency"
            enable_daily = True
            enable_weekly = True
            enable_whale = False
        
        # Create new mapping
        mappings[chat_id] = ChatMapping(
            models=[ModelConfig(
                platform=platform,
                platform_account_id=account_id,
                nickname=nickname
            )],
            chat_type=chat_type,
            enable_daily_report=enable_daily,
            enable_weekly_report=enable_weekly,
            enable_whale_alerts=enable_whale,
            enable_chatter_report=False,  # Default off, enable with /config
            whale_alert_threshold=4,  # Default threshold: 4+
        )
        storage.save(mappings)
        
        logger.info(f"Linked chat {chat_id} to {platform} account {account_id} ({nickname}) as {chat_type}")
        
        display_name = nickname or account_id
        
        config_msg = (
            f"✅ Chat linked to model **{display_name}** (`{account_id}`) on `{platform.title()}`\n\n"
            f"**Configuration ({chat_type}):**\n"
            f"• Daily reports: {'✅' if enable_daily else '❌'}\n"
            f"• Weekly reports: {'✅' if enable_weekly else '❌'}\n"
            f"• Whale alerts: {'✅' if enable_whale else '❌'}\n\n"
            f"Use `/link onlyfans 123456 agency AnotherModel` to add more models\n"
            "Use `/config` to customize settings"
        )
        
        await update.message.reply_text(config_msg, parse_mode="Markdown")


async def cmd_unlink(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /unlink command to remove model connection."""
    chat_id = str(update.effective_chat.id)
    
    mappings = storage.load()
    
    if chat_id not in mappings:
        await update.message.reply_text(
            "❌ This chat is not linked to any models.",
            parse_mode="Markdown"
        )
        return
    
    mapping = mappings[chat_id]
    
    # If no model specified, show usage
    if len(context.args) == 0:
        model_list = "\n".join([
            f"• `{m.nickname or m.platform_account_id}` ({m.platform_account_id})"
            for m in mapping.models
        ])
        await update.message.reply_text(
            f"**Linked Models:**\n{model_list}\n\n"
            f"**Usage:** `/unlink <model_name_or_id>`\n"
            f"**Example:** `/unlink {mapping.models[0].nickname or mapping.models[0].platform_account_id}`\n\n"
            f"Or use `/unlink all` to remove all models",
            parse_mode="Markdown"
        )
        return
    
    model_identifier = " ".join(context.args).lower()
    
    # Special case: unlink all
    if model_identifier == "all":
        model_count = len(mapping.models)
        del mappings[chat_id]
        storage.save(mappings)
        logger.info(f"Unlinked all models from chat {chat_id}")
        await update.message.reply_text(
            f"✅ Removed all {model_count} model(s) from this group.\n\n"
            f"Use `/link` to add models again.",
            parse_mode="Markdown"
        )
        return
    
    # Find and remove specific model
    model_to_remove = None
    for model in mapping.models:
        if (model.platform_account_id.lower() == model_identifier or 
            (model.nickname and model.nickname.lower() == model_identifier)):
            model_to_remove = model
            break
    
    if not model_to_remove:
        model_list = ", ".join([
            f"`{m.nickname or m.platform_account_id}`" for m in mapping.models
        ])
        await update.message.reply_text(
            f"❌ Model `{model_identifier}` not found.\n\n"
            f"**Linked models:** {model_list}\n\n"
            f"Use `/models` to see all linked models",
            parse_mode="Markdown"
        )
        return
    
    # Remove the model
    mapping.models.remove(model_to_remove)
    
    # If no models left, delete the entire mapping
    if not mapping.models:
        del mappings[chat_id]
        storage.save(mappings)
        logger.info(f"Removed last model from chat {chat_id}, deleted mapping")
        await update.message.reply_text(
            f"✅ Removed **{model_to_remove.nickname or model_to_remove.platform_account_id}**\n\n"
            f"No models left in this group.\n"
            f"Use `/link` to add models.",
            parse_mode="Markdown"
        )
    else:
        # Update mapping with remaining models
        mappings[chat_id] = mapping
        storage.save(mappings)
        logger.info(
            f"Removed model {model_to_remove.platform_account_id} from chat {chat_id}, "
            f"{len(mapping.models)} model(s) remaining"
        )
        
        remaining_models = ", ".join([
            f"`{m.nickname or m.platform_account_id}`" for m in mapping.models
        ])
        
        await update.message.reply_text(
            f"✅ Removed **{model_to_remove.nickname or model_to_remove.platform_account_id}**\n\n"
            f"**Remaining models ({len(mapping.models)}):** {remaining_models}",
            parse_mode="Markdown"
        )



async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /today command - show current OnlyFans day revenue (1 AM to NOW)."""
    chat_id = str(update.effective_chat.id)
    
    # Check if chat is linked
    mappings = storage.load()
    if chat_id not in mappings:
        await update.message.reply_text(
            "❌ This chat is not linked to any model.\n\n"
            "Use `/link <platform> <account_id>` first.\n"
            "Example: `/link onlyfans maxes agency`",
            parse_mode="Markdown"
        )
        return
    
    mapping = mappings[chat_id]
    
    # Check if user specified a model: /today maxes or /today Maxes
    specific_model = context.args[0].lower() if len(context.args) > 0 else None
    
    # SECURITY: Only allow stats for models linked to this group
    models_to_show = []
    
    if specific_model:
        # Find the specific model by nickname OR account_id
        for model in mapping.models:
            if (model.platform_account_id.lower() == specific_model or 
                (model.nickname and model.nickname.lower() == specific_model)):
                models_to_show.append(model)
                break
        
        if not models_to_show:
            model_list = ", ".join([
                f"`{m.nickname or m.platform_account_id}`" for m in mapping.models
            ])
            first_model_example = mapping.models[0].nickname or mapping.models[0].platform_account_id
            await update.message.reply_text(
                f"❌ Model `{specific_model}` is not linked to this group.\n\n"
                f"**Linked models:** {model_list}\n\n"
                f"Use `/today` for all models or `/today {first_model_example}` for specific model",
                parse_mode="Markdown"
            )
            return
    else:
        # Show all models
        models_to_show = mapping.models
    
    # Get today's revenue (1 AM Berlin to NOW)
    try:
        start_utc, end_utc = OnlyFansCalendar.get_current_of_day()
        
        # Fetch stats for each model
        all_stats = []
        for model in models_to_show:
            stats = om_client.calculate_revenue(
                model.platform,
                model.platform_account_id,
                start_utc,
                end_utc
            )
            all_stats.append((model, stats))
        
        # Format response
        if len(all_stats) == 1:
            # Single model
            model, stats = all_stats[0]
            display_name = model.nickname or model.platform_account_id
            msg = MessageFormatter.format_revenue(
                stats,
                display_name,
                model.platform,
                "Today's Revenue (1 AM - Now)"
            )
        else:
            # Multiple models - combined view
            total_revenue = sum(s.total_amount for _, s in all_stats)
            total_subs = sum(s.new_subscribers or 0 for _, s in all_stats)
            
            start_berlin = start_utc.astimezone(BERLIN_TZ)
            end_berlin = end_utc.astimezone(BERLIN_TZ)
            
            msg = f"📊 *Today's Revenue (1 AM - Now)*\n\n"
            msg += f"**All Models Combined:**\n"
            msg += f"💰 Total Revenue: *${total_revenue:,.2f}*\n"
            if total_subs > 0:
                msg += f"👥 New Subscribers: *{total_subs}*\n"
            msg += f"\n📅 Period: {start_berlin.strftime('%d.%m.%Y %H:%M')} - {end_berlin.strftime('%d.%m.%Y %H:%M')}\n\n"
            
            msg += "**Breakdown by Model:**\n"
            for model, stats in all_stats:
                display_name = model.nickname or model.platform_account_id
                msg += f"\n🎯 **{display_name}**:\n"
                msg += f"   💰 ${stats.total_amount:,.2f}"
                if stats.new_subscribers and stats.new_subscribers > 0:
                    msg += f" | 👥 {stats.new_subscribers} subs"
                msg += "\n"
            
            # Show example with first model name
            first_model_example = models_to_show[0].nickname or models_to_show[0].platform_account_id
            msg += f"\nUse `/today {first_model_example}` to see detailed stats for a specific model"
        
        await update.message.reply_text(msg, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error fetching today's revenue: {e}")
        error_msg = MessageFormatter.format_error(
            "Failed to fetch revenue data from OnlyMonster API.\n"
            "Please check your API token and account IDs."
        )
        await update.message.reply_text(error_msg, parse_mode="Markdown")


async def cmd_yesterday(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /yesterday command - show previous OnlyFans day revenue."""
    chat_id = str(update.effective_chat.id)
    
    # Check if chat is linked
    mappings = storage.load()
    if chat_id not in mappings:
        await update.message.reply_text(
            "❌ This chat is not linked to any model.\n\n"
            "Use `/link <platform> <account_id>` first.\n"
            "Example: `/link onlyfans 454315739`",
            parse_mode="Markdown"
        )
        return
    
    mapping = mappings[chat_id]
    
    # Get yesterday's revenue
    try:
        start_utc, end_utc = OnlyFansCalendar.get_previous_of_day()
        stats = om_client.calculate_revenue(
            mapping.platform,
            mapping.platform_account_id,
            start_utc,
            end_utc
        )
        
        msg = MessageFormatter.format_revenue(
            stats,
            mapping.platform_account_id,
            mapping.platform,
            "Yesterday's Revenue"
        )
        
        await update.message.reply_text(msg, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error fetching yesterday's revenue: {e}")
        error_msg = MessageFormatter.format_error(
            "Failed to fetch revenue data from OnlyMonster API.\n"
            "Please check your API token and account ID."
        )
        await update.message.reply_text(error_msg, parse_mode="Markdown")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stats command - show current stats."""
    # For now, just call today
    await cmd_today(update, context)


async def cmd_week(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /week command - show last 7 days revenue."""
    chat_id = str(update.effective_chat.id)
    
    # Check if chat is linked
    mappings = storage.load()
    if chat_id not in mappings:
        await update.message.reply_text(
            "❌ This chat is not linked to any model.\n\n"
            "Use `/link <platform> <account_id>` first.\n"
            "Example: `/link onlyfans 454315739`",
            parse_mode="Markdown"
        )
        return
    
    mapping = mappings[chat_id]
    
    # Get last 7 days revenue
    try:
        today = datetime.now(BERLIN_TZ).date()
        end_day = today - timedelta(days=1)
        start_day = end_day - timedelta(days=6)
        
        start_utc, _ = OnlyFansCalendar.get_of_day_range(start_day)
        _, end_utc = OnlyFansCalendar.get_of_day_range(end_day)
        
        stats = om_client.calculate_revenue(
            mapping.platform,
            mapping.platform_account_id,
            start_utc,
            end_utc
        )
        
        msg = MessageFormatter.format_revenue(
            stats,
            mapping.platform_account_id,
            mapping.platform,
            "📊 Weekly Revenue (Last 7 Days)"
        )
        
        await update.message.reply_text(msg, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error fetching weekly revenue: {e}")
        error_msg = MessageFormatter.format_error(
            "Failed to fetch revenue data from OnlyMonster API.\n"
            "Please check your API token and account ID."
        )
        await update.message.reply_text(error_msg, parse_mode="Markdown")


async def cmd_config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /config command - show and modify chat configuration."""
    chat_id = str(update.effective_chat.id)
    
    mappings = storage.load()
    if chat_id not in mappings:
        await update.message.reply_text(
            "❌ This chat is not linked to any model.\n\n"
            "Use `/link <platform> <account_id>` first.",
            parse_mode="Markdown"
        )
        return
    
    mapping = mappings[chat_id]
    
    # If no arguments, show current config
    if len(context.args) == 0:
        # Build model list with details
        model_details = []
        for idx, model in enumerate(mapping.models, 1):
            display_name = model.nickname or model.platform_account_id
            model_details.append(
                f"{idx}. **{display_name}** (`{model.platform_account_id}`) on `{model.platform}`"
            )
        models_text = "\n".join(model_details)
        
        config_msg = (
            f"⚙️ **Configuration**\n\n"
            f"**Chat Type:** `{mapping.chat_type}`\n\n"
            f"**Linked Models ({len(mapping.models)}):**\n{models_text}\n\n"
            f"**Enabled Features:**\n"
            f"• Daily reports (1 AM): {'✅' if mapping.enable_daily_report else '❌'}\n"
            f"• Weekly reports (Mon 1 AM): {'✅' if mapping.enable_weekly_report else '❌'}\n"
            f"• Whale alerts: {'✅' if mapping.enable_whale_alerts else '❌'}\n"
            f"• Chatter report (1 AM): {'✅' if mapping.enable_chatter_report else '❌'}\n"
            f"• Whale threshold: Score ≥ {mapping.whale_alert_threshold}\n\n"
            "**Modify Settings:**\n"
            "`/config daily on|off` - Toggle daily reports\n"
            "`/config weekly on|off` - Toggle weekly reports\n"
            "`/config whale on|off` - Toggle whale alerts\n"
            "`/config chatter_report on|off` - Toggle chatter performance report\n"
            "`/config threshold <0-5>` - Set whale alert threshold\n\n"
            "**Manage Models:**\n"
            "`/models` - List all linked models\n"
            "`/unlink <model>` - Remove a specific model"
        )
        await update.message.reply_text(config_msg, parse_mode="Markdown")
        return
    
    # Modify settings
    setting = context.args[0].lower()
    
    if setting == "daily" and len(context.args) >= 2:
        value = context.args[1].lower() == "on"
        mapping.enable_daily_report = value
        mappings[chat_id] = mapping
        storage.save(mappings)
        await update.message.reply_text(
            f"✅ Daily reports: {'Enabled' if value else 'Disabled'}",
            parse_mode="Markdown"
        )
    
    elif setting == "weekly" and len(context.args) >= 2:
        value = context.args[1].lower() == "on"
        mapping.enable_weekly_report = value
        mappings[chat_id] = mapping
        storage.save(mappings)
        await update.message.reply_text(
            f"✅ Weekly reports: {'Enabled' if value else 'Disabled'}",
            parse_mode="Markdown"
        )
    
    elif setting == "whale" and len(context.args) >= 2:
        value = context.args[1].lower() == "on"
        mapping.enable_whale_alerts = value
        mappings[chat_id] = mapping
        storage.save(mappings)
        await update.message.reply_text(
            f"✅ Whale alerts: {'Enabled' if value else 'Disabled'}",
            parse_mode="Markdown"
        )
    
    elif setting == "chatter_report" and len(context.args) >= 2:
        value = context.args[1].lower() == "on"
        mapping.enable_chatter_report = value
        mappings[chat_id] = mapping
        storage.save(mappings)
        
        if value:
            model_count = len(mapping.models)
            model_names = ", ".join([m.nickname or m.platform_account_id for m in mapping.models])
            await update.message.reply_text(
                f"✅ **Chatter Performance Report: Enabled**\n\n"
                f"Daily chatter reports will be sent at 1:00 AM Berlin time.\n\n"
                f"📊 Tracking chatters across {model_count} model(s):\n{model_names}\n\n"
                f"💡 Tip: Add more models with `/link onlyfans <id> chatter <name>`",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                f"✅ Chatter Performance Report: Disabled",
                parse_mode="Markdown"
            )
    
    elif setting == "threshold" and len(context.args) >= 2:
        try:
            threshold = int(context.args[1])
            if 0 <= threshold <= 5:
                mapping.whale_alert_threshold = threshold
                mappings[chat_id] = mapping
                storage.save(mappings)
                await update.message.reply_text(
                    f"✅ Whale alert threshold set to: {threshold}",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    "❌ Threshold must be between 0 and 5",
                    parse_mode="Markdown"
                )
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid threshold value. Use a number 0-5",
                parse_mode="Markdown"
            )
    
    else:
        await update.message.reply_text(
            "❌ Invalid config command.\n\n"
            "Use `/config` to see available options.",
            parse_mode="Markdown"
        )


async def cmd_models(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /models command - list all linked models."""
    chat_id = str(update.effective_chat.id)
    
    mappings = storage.load()
    if chat_id not in mappings:
        await update.message.reply_text(
            "❌ This chat is not linked to any model.\n\n"
            "Use `/link <platform> <account_id>` first.",
            parse_mode="Markdown"
        )
        return
    
    mapping = mappings[chat_id]
    
    if not mapping.models:
        await update.message.reply_text(
            "❌ No models linked to this chat.",
            parse_mode="Markdown"
        )
        return
    
    # Build detailed model list
    model_list = f"📋 **Linked Models ({len(mapping.models)})**\n\n"
    
    for idx, model in enumerate(mapping.models, 1):
        display_name = model.nickname or model.platform_account_id
        model_list += f"{idx}. **{display_name}**\n"
        model_list += f"   • Platform: `{model.platform}`\n"
        model_list += f"   • Account ID: `{model.platform_account_id}`\n"
        if model.nickname:
            model_list += f"   • Nickname: `{model.nickname}`\n"
        model_list += "\n"
    
    model_list += f"**Chat Type:** `{mapping.chat_type}`\n\n"
    model_list += "**Quick Access:**\n"
    
    # Show example commands for each model
    for model in mapping.models[:3]:  # Show first 3 models
        display_name = model.nickname or model.platform_account_id
        model_list += f"• `/today {display_name}` - View {display_name}'s stats\n"
    
    if len(mapping.models) > 3:
        model_list += f"• ... and {len(mapping.models) - 3} more\n"
    
    model_list += f"\n`/today` - View all models combined"
    
    await update.message.reply_text(model_list, parse_mode="Markdown")


# ============================================================================
# Scheduled Jobs
# ============================================================================


async def daily_report_job(context: CallbackContext) -> None:
    """
    Scheduled job that runs daily at 1:00 AM Berlin time.
    Sends yesterday's revenue report to all linked chats (if enabled).
    """
    logger.info("Starting daily report job")
    
    mappings = storage.load()
    
    if not mappings:
        logger.info("No chat mappings found for daily report")
        return
    
    start_utc, end_utc = OnlyFansCalendar.get_previous_of_day()
    
    for chat_id, mapping in mappings.items():
        # Skip if daily reports are disabled for this chat
        if not mapping.enable_daily_report:
            logger.info(f"Daily report disabled for chat {chat_id}, skipping")
            continue
        
        try:
            stats = om_client.calculate_revenue(
                mapping.platform,
                mapping.platform_account_id,
                start_utc,
                end_utc
            )
            
            msg = MessageFormatter.format_revenue(
                stats,
                mapping.platform_account_id,
                mapping.platform,
                "📅 Daily Revenue Report"
            )
            
            await context.bot.send_message(
                chat_id=int(chat_id),
                text=msg,
                parse_mode="Markdown"
            )
            
            logger.info(f"Sent daily report to chat {chat_id}")
            
        except Exception as e:
            logger.error(f"Failed to send daily report to chat {chat_id}: {e}")


async def weekly_report_job(context: CallbackContext) -> None:
    """
    Scheduled job that runs weekly on Mondays at 1:00 AM Berlin time.
    Sends last 7 days revenue report to all linked chats (if enabled).
    """
    logger.info("Starting weekly report job")
    
    mappings = storage.load()
    
    if not mappings:
        logger.info("No chat mappings found for weekly report")
        return
    
    # Calculate the last 7 complete OnlyFans days
    today = datetime.now(BERLIN_TZ).date()
    # End of yesterday's OF day
    end_day = today - timedelta(days=1)
    # Start of 7 days ago
    start_day = end_day - timedelta(days=6)
    
    start_utc, _ = OnlyFansCalendar.get_of_day_range(start_day)
    _, end_utc = OnlyFansCalendar.get_of_day_range(end_day)
    
    for chat_id, mapping in mappings.items():
        # Skip if weekly reports are disabled for this chat
        if not mapping.enable_weekly_report:
            logger.info(f"Weekly report disabled for chat {chat_id}, skipping")
            continue
        
        try:
            stats = om_client.calculate_revenue(
                mapping.platform,
                mapping.platform_account_id,
                start_utc,
                end_utc
            )
            
            msg = MessageFormatter.format_revenue(
                stats,
                mapping.platform_account_id,
                mapping.platform,
                "📊 Weekly Revenue Report (Last 7 Days)"
            )
            
            await context.bot.send_message(
                chat_id=int(chat_id),
                text=msg,
                parse_mode="Markdown"
            )
            
            logger.info(f"Sent weekly report to chat {chat_id}")
            
        except Exception as e:
            logger.error(f"Failed to send weekly report to chat {chat_id}: {e}")


async def chatter_report_job(context: CallbackContext) -> None:
    """
    Scheduled job that runs daily at 1:00 AM Berlin time.
    Sends yesterday's chatter performance report to groups with chatter_report enabled.
    Combines data from ALL linked models in the group.
    """
    logger.info("Starting chatter report job")
    
    mappings = storage.load()
    
    if not mappings:
        logger.info("No chat mappings found for chatter report")
        return
    
    # Initialize chatter performance client
    chatter_client = ChatterPerformanceClient()
    
    # Get yesterday's date for the report title
    yesterday = (datetime.now(BERLIN_TZ) - timedelta(days=1)).strftime("%Y-%m-%d")
    
    for chat_id, mapping in mappings.items():
        # Only send if chatter reports are enabled
        if not mapping.enable_chatter_report:
            logger.info(f"Chatter reports disabled for chat {chat_id}, skipping")
            continue
        
        if not mapping.models:
            logger.warning(f"No models linked to chat {chat_id}, skipping chatter report")
            continue
        
        try:
            # Fetch chatter performance from ALL linked models
            all_chatter_stats = []
            model_names = []
            
            for model in mapping.models:
                try:
                    chatter_stats = chatter_client.get_yesterday_performance(
                        model.platform,
                        model.platform_account_id
                    )
                    
                    # Add all chatters from this model
                    all_chatter_stats.extend(chatter_stats)
                    model_names.append(model.nickname or model.platform_account_id)
                    
                    logger.info(
                        f"Fetched {len(chatter_stats)} chatters from {model.platform_account_id}"
                    )
                    
                except Exception as e:
                    logger.error(
                        f"Failed to fetch chatter stats for {model.platform_account_id}: {e}"
                    )
                    continue
            
            if not all_chatter_stats:
                logger.warning(f"No chatter stats found for chat {chat_id}")
                continue
            
            # Combine chatters with same name (across multiple models)
            from collections import defaultdict
            combined_chatters = defaultdict(lambda: {
                'total_sales': 0,
                'total_messages': 0,
                'template_messages': 0,
                'manual_messages': 0,
                'response_times': [],
                'conversions': []
            })
            
            for stats in all_chatter_stats:
                chatter = combined_chatters[stats.chatter_name]
                chatter['total_sales'] += stats.total_sales
                chatter['total_messages'] += stats.total_messages
                chatter['template_messages'] += stats.template_messages
                chatter['manual_messages'] += stats.manual_messages
                chatter['response_times'].append(stats.avg_response_time_seconds)
                chatter['conversions'].append(stats.ppv_conversion_rate)
            
            # Convert back to ChatterStats objects
            from chatter_tracker import ChatterStats
            final_stats = []
            for name, data in combined_chatters.items():
                avg_response = sum(data['response_times']) / len(data['response_times'])
                avg_conversion = sum(data['conversions']) / len(data['conversions'])
                
                final_stats.append(ChatterStats(
                    chatter_name=name,
                    total_sales=data['total_sales'],
                    avg_response_time_seconds=avg_response,
                    ppv_conversion_rate=avg_conversion,
                    total_messages=data['total_messages'],
                    template_messages=data['template_messages'],
                    manual_messages=data['manual_messages']
                ))
            
            # Sort by sales (highest first)
            final_stats.sort(key=lambda x: x.total_sales, reverse=True)
            
            # Format report with all models listed
            models_list = ", ".join(model_names)
            report = format_chatter_report(final_stats, f"All Models ({models_list})", yesterday)
            
            # Send report
            await context.bot.send_message(
                chat_id=int(chat_id),
                text=report,
                parse_mode="Markdown"
            )
            logger.info(f"Sent combined chatter report to chat {chat_id} ({len(final_stats)} chatters)")
            
        except Exception as e:
            logger.error(f"Failed to send chatter report to chat {chat_id}: {e}")


async def whale_alert_job(context: CallbackContext) -> None:
    """
    Check for high-value fans online and send whale alerts.
    Runs every 5 minutes.
    """
    logger.info("Checking for whale alerts")
    
    mappings = storage.load()
    
    if not mappings:
        return
    
    for chat_id, mapping in mappings.items():
        # Skip if whale alerts are disabled
        if not mapping.enable_whale_alerts:
            continue
        
        try:
            # Get online fans with high buying power
            url = (
                f"{om_client.base_url}/api/v0/platforms/{mapping.platform.lower()}"
                f"/accounts/{mapping.platform_account_id}/fans/online"
            )
            
            response = om_client.session.get(url, timeout=20)
            if response.status_code != 200:
                logger.debug(f"Whale check failed for {mapping.platform_account_id}: {response.status_code}")
                continue
            
            data = response.json()
            fans = data.get("fans", []) or []
            
            # Filter high-value fans
            for fan in fans:
                buying_power = fan.get("buying_power", 0)
                fan_username = fan.get("username", "Unknown")
                fan_id = fan.get("id", "")
                last_spent = fan.get("last_purchase_amount", 0)
                
                # Check if fan meets threshold
                if buying_power >= mapping.whale_alert_threshold:
                    # Check if we already alerted about this fan recently
                    # (to avoid spam) - using context.bot_data as temporary storage
                    alert_key = f"whale_{chat_id}_{fan_id}"
                    last_alert = context.bot_data.get(alert_key, 0)
                    current_time = datetime.now().timestamp()
                    
                    # Only alert if we haven't alerted in last 30 minutes
                    if current_time - last_alert > 1800:  # 30 minutes
                        whale_msg = (
                            f"🐋 *WHALE ALERT!*\n\n"
                            f"High-value fan is online!\n\n"
                            f"👤 Username: `{fan_username}`\n"
                            f"⭐ Buying Power: *{buying_power}/5*\n"
                            f"💰 Last Purchase: *${last_spent:.2f}*\n"
                            f"🎯 Model: `{mapping.platform_account_id}`\n\n"
                            f"🚀 *Engage NOW!*"
                        )
                        
                        await context.bot.send_message(
                            chat_id=int(chat_id),
                            text=whale_msg,
                            parse_mode="Markdown"
                        )
                        
                        # Mark as alerted
                        context.bot_data[alert_key] = current_time
                        logger.info(f"Sent whale alert to chat {chat_id} for fan {fan_username}")
        
        except Exception as e:
            logger.error(f"Whale alert check failed for chat {chat_id}: {e}")


# ============================================================================
# Error Handler
# ============================================================================


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors caused by updates."""
    logger.error(f"Update {update} caused error {context.error}")


# ============================================================================
# Main Application
# ============================================================================


def main() -> None:
    """Start the bot."""
    logger.info("Starting ValeoBot...")
    
    # Create application
    application = Application.builder().token(TG_BOT_TOKEN).build()
    
    # Register command handlers
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("link", cmd_link))
    application.add_handler(CommandHandler("unlink", cmd_unlink))
    application.add_handler(CommandHandler("today", cmd_today))
    application.add_handler(CommandHandler("yesterday", cmd_yesterday))
    application.add_handler(CommandHandler("week", cmd_week))
    application.add_handler(CommandHandler("stats", cmd_stats))
    application.add_handler(CommandHandler("config", cmd_config))
    application.add_handler(CommandHandler("models", cmd_models))
    
    # Register error handler
    application.add_error_handler(error_handler)
    
    # Get job queue
    job_queue = application.job_queue
    
    # Only schedule jobs if job_queue is available
    if job_queue:
        # Schedule daily job (runs at 1:00 AM Berlin time every day)
        from datetime import time
        job_queue.run_daily(
            daily_report_job,
            time=time(hour=1, minute=0, tzinfo=BERLIN_TZ),
            name="daily-revenue-report"
        )
        
        # Schedule weekly job (runs at 1:00 AM Berlin time every Monday)
        from datetime import time as dtime
        job_queue.run_daily(
            weekly_report_job,
            time=dtime(hour=1, minute=0, tzinfo=BERLIN_TZ),
            days=(0,),  # 0 = Monday
            name="weekly-revenue-report"
        )
        
        # Schedule whale alert job (runs every 5 minutes)
        job_queue.run_repeating(
            whale_alert_job,
            interval=300,  # 5 minutes in seconds
            first=10,  # Start 10 seconds after bot starts
            name="whale-alerts"
        )
        
        # Schedule chatter report job (runs at 1:00 AM Berlin time every day)
        job_queue.run_daily(
            chatter_report_job,
            time=time(hour=1, minute=0, tzinfo=BERLIN_TZ),
            name="chatter-performance-report"
        )
        
        logger.info("Scheduled jobs registered successfully")
    else:
        logger.warning("JobQueue not available - scheduled reports will not work")
    
    logger.info("ValeoBot is running! Press Ctrl+C to stop.")
    
    # Start the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
