"""
Chatter Performance Tracker for ValeoBot
Fetches and reports chatter performance metrics from OnlyMonster API
"""

import os
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dataclasses import dataclass
from typing import List, Optional
import requests

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
OM_API_TOKEN = os.getenv("OM_API_TOKEN")
OM_BASE_URL = os.getenv("OM_BASE_URL", "https://omapi.onlymonster.ai")
BERLIN_TZ = ZoneInfo("Europe/Berlin")

# Minimum messages required to appear in report
MIN_MESSAGES_THRESHOLD = 50


@dataclass
class ChatterStats:
    """Represents performance stats for a single chatter."""
    chatter_name: str
    total_sales: float
    avg_response_time_seconds: float
    ppv_conversion_rate: float
    total_messages: int
    template_messages: int
    manual_messages: int
    
    @property
    def avg_response_formatted(self) -> str:
        """Format average response time as MM:SS"""
        minutes = int(self.avg_response_time_seconds // 60)
        seconds = int(self.avg_response_time_seconds % 60)
        return f"{minutes}:{seconds:02d}min"


class ChatterPerformanceClient:
    """Client for fetching chatter performance data from OnlyMonster API."""
    
    def __init__(self):
        self.base_url = OM_BASE_URL
        self.api_token = OM_API_TOKEN
        self.session = requests.Session()
        self.session.headers.update({
            "x-om-auth-token": self.api_token,
            "accept": "application/json"
        })
    
    def get_chatter_performance(
        self, 
        platform: str, 
        account_id: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[ChatterStats]:
        """
        Fetch chatter performance data from OnlyMonster API.
        
        Args:
            platform: Platform name (e.g., 'onlyfans')
            account_id: Platform account ID
            start_time: Start datetime (UTC)
            end_time: End datetime (UTC)
        
        Returns:
            List of ChatterStats objects
        """
        try:
            # Format dates for API
            start_date = start_time.strftime("%Y-%m-%d")
            end_date = end_time.strftime("%Y-%m-%d")
            
            # OnlyMonster API endpoint for chatter performance
            # Note: This endpoint structure is based on common API patterns
            # Adjust if OnlyMonster uses different endpoint structure
            url = f"{self.base_url}/api/v0/platforms/{platform}/accounts/{account_id}/chatter-performance"
            
            params = {
                "start_date": start_date,
                "end_date": end_date
            }
            
            logger.info(f"Fetching chatter performance: {url}")
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            # Parse response and create ChatterStats objects
            chatter_stats = []
            
            # Expected API response format (adjust based on actual OnlyMonster API):
            # {
            #   "chatters": [
            #     {
            #       "name": "Marc",
            #       "total_sales": 1234.56,
            #       "avg_response_time": 85.5,  # seconds
            #       "ppv_conversion_rate": 0.67,  # 67%
            #       "total_messages": 555,
            #       "template_messages": 45,
            #       "manual_messages": 510
            #     },
            #     ...
            #   ]
            # }
            
            for chatter_data in data.get("chatters", []):
                stats = ChatterStats(
                    chatter_name=chatter_data.get("name", "Unknown"),
                    total_sales=float(chatter_data.get("total_sales", 0)),
                    avg_response_time_seconds=float(chatter_data.get("avg_response_time", 0)),
                    ppv_conversion_rate=float(chatter_data.get("ppv_conversion_rate", 0)),
                    total_messages=int(chatter_data.get("total_messages", 0)),
                    template_messages=int(chatter_data.get("template_messages", 0)),
                    manual_messages=int(chatter_data.get("manual_messages", 0))
                )
                
                # Only include chatters with minimum message threshold
                if stats.total_messages >= MIN_MESSAGES_THRESHOLD:
                    chatter_stats.append(stats)
            
            # Sort by total sales (highest first)
            chatter_stats.sort(key=lambda x: x.total_sales, reverse=True)
            
            logger.info(f"Found {len(chatter_stats)} chatters with {MIN_MESSAGES_THRESHOLD}+ messages")
            return chatter_stats
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error fetching chatter performance: {e}")
            logger.error(f"Response: {e.response.text if e.response else 'No response'}")
            raise
        except Exception as e:
            logger.error(f"Error fetching chatter performance: {e}")
            raise
    
    def get_yesterday_performance(self, platform: str, account_id: str) -> List[ChatterStats]:
        """
        Get chatter performance for yesterday (OnlyFans day: 1 AM to 1 AM Berlin time).
        
        Args:
            platform: Platform name
            account_id: Platform account ID
        
        Returns:
            List of ChatterStats for yesterday
        """
        # Get yesterday's OnlyFans day (1 AM to 1 AM Berlin time)
        now_berlin = datetime.now(BERLIN_TZ)
        yesterday = now_berlin.date() - timedelta(days=1)
        
        # Yesterday: 1:00 AM to 12:59:59 AM (23:59:59)
        start_local = datetime(
            yesterday.year, yesterday.month, yesterday.day, 1, 0, 0,
            tzinfo=BERLIN_TZ
        )
        end_local = datetime(
            now_berlin.year, now_berlin.month, now_berlin.day, 0, 59, 59,
            tzinfo=BERLIN_TZ
        )
        
        # Convert to UTC for API
        start_utc = start_local.astimezone(ZoneInfo("UTC"))
        end_utc = end_local.astimezone(ZoneInfo("UTC"))
        
        return self.get_chatter_performance(platform, account_id, start_utc, end_utc)


def format_chatter_report(chatter_stats: List[ChatterStats], model_name: str, date: str) -> str:
    """
    Format chatter performance data into a Telegram message.
    
    Args:
        chatter_stats: List of ChatterStats objects
        model_name: Name of the model
        date: Date string for the report
    
    Returns:
        Formatted message string
    """
    if not chatter_stats:
        return (
            f"👥 *Chatter Performance Report*\n"
            f"🎯 Model: {model_name}\n"
            f"📅 Date: {date}\n\n"
            f"No chatters met the minimum requirement of {MIN_MESSAGES_THRESHOLD} messages."
        )
    
    # Calculate totals
    total_sales = sum(c.total_sales for c in chatter_stats)
    total_messages = sum(c.total_messages for c in chatter_stats)
    avg_conversion = sum(c.ppv_conversion_rate for c in chatter_stats) / len(chatter_stats)
    
    message = f"👥 *Chatter Performance Report*\n\n"
    message += f"🎯 Model: *{model_name}*\n"
    message += f"📅 Date: {date}\n"
    message += f"💰 Total Sales: *${total_sales:,.2f}*\n"
    message += f"📨 Total Messages: *{total_messages:,}*\n"
    message += f"📊 Avg PPV Conversion: *{avg_conversion*100:.1f}%*\n\n"
    message += "━━━━━━━━━━━━━━━━━━\n\n"
    
    # Add individual chatter stats
    for idx, stats in enumerate(chatter_stats, 1):
        medal = "👑" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
        
        message += f"{medal} *{stats.chatter_name}*\n"
        message += f"💰 Sales: *${stats.total_sales:,.2f}*\n"
        message += f"⚡ Avg Response: *{stats.avg_response_formatted}*\n"
        message += f"🎯 PPV Conversion: *{stats.ppv_conversion_rate*100:.1f}%*\n"
        message += f"📨 Messages: *{stats.total_messages:,}*\n"
        message += f"📩 Templates: *{stats.template_messages:,}*\n\n"
    
    message += "━━━━━━━━━━━━━━━━━━\n"
    message += f"_Minimum {MIN_MESSAGES_THRESHOLD} messages required to appear in this report_"
    
    return message


if __name__ == "__main__":
    # Test the chatter performance client
    client = ChatterPerformanceClient()
    
    # Test with sample data
    try:
        stats = client.get_yesterday_performance("onlyfans", "447717014")
        report = format_chatter_report(stats, "Megan", "2025-12-26")
        print(report)
    except Exception as e:
        logger.error(f"Test failed: {e}")