import logging
import re
import os
import tempfile
import asyncio
import concurrent.futures
import json
from datetime import datetime, timedelta
from collections import defaultdict
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp
import requests

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "default_token")
BOT_USERNAME = "eyysavebot"
MAX_FILE_SIZE = 50 * 1024 * 1024

ANALYTICS_FILE = "analytics.json"

def load_analytics():
    try:
        with open(ANALYTICS_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {
            "users": {},
            "downloads": {"tiktok": 0, "instagram": 0, "total": 0},
            "daily_stats": {},
            "monthly_stats": {}
        }

def save_analytics(data):
    with open(ANALYTICS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def track_user(user_id, username, first_name):
    data = load_analytics()
    today = datetime.now().strftime("%Y-%m-%d")
    month = datetime.now().strftime("%Y-%m")
    
    if str(user_id) not in data["users"]:
        data["users"][str(user_id)] = {
            "username": username,
            "first_name": first_name,
            "first_seen": today,
            "last_seen": today,
            "downloads": 0
        }
    else:
        data["users"][str(user_id)]["last_seen"] = today
    
    if today not in data["daily_stats"]:
        data["daily_stats"][today] = {"users": 0, "downloads": 0}
    if month not in data["monthly_stats"]:
        data["monthly_stats"][month] = {"users": 0, "downloads": 0}
    
    save_analytics(data)

def track_download(platform):
    data = load_analytics()
    today = datetime.now().strftime("%Y-%m-%d")
    month = datetime.now().strftime("%Y-%m")
    
    data["downloads"][platform] += 1
    data["downloads"]["total"] += 1
    
    if today not in data["daily_stats"]:
        data["daily_stats"][today] = {"users": 0, "downloads": 0}
    if month not in data["monthly_stats"]:
        data["monthly_stats"][month] = {"users": 0, "downloads": 0}
    
    data["daily_stats"][today]["downloads"] += 1
    data["monthly_stats"][month]["downloads"] += 1
    
    save_analytics(data)

def get_stats():
    data = load_analytics()
    total_users = len(data["users"])
    total_downloads = data["downloads"]["total"]
    tiktok_downloads = data["downloads"]["tiktok"]
    instagram_downloads = data["downloads"]["instagram"]
    
    today = datetime.now().strftime("%Y-%m-%d")
    month = datetime.now().strftime("%Y-%m")
    
    today_downloads = data["daily_stats"].get(today, {}).get("downloads", 0)
    month_downloads = data["monthly_stats"].get(month, {}).get("downloads", 0)
    
    return {
        "total_users": total_users,
        "total_downloads": total_downloads,
        "tiktok_downloads": tiktok_downloads,
        "instagram_downloads": instagram_downloads,
        "today_downloads": today_downloads,
        "month_downloads": month_downloads
    }

def is_tiktok_url(url: str) -> bool:
    return 'tiktok.com' in url.lower()

def is_instagram_url(url: str) -> bool:
    return 'instagram.com' in url.lower()

def download_video(url: str, platform: str) -> tuple[str, str]:
    temp_dir = tempfile.mkdtemp()
    output_path = os.path.join(temp_dir, f"video.{platform}")
    
    if platform == "tiktok":
        tiktok_methods = [
            {
                'format': 'best[height<=1080]',
                'outtmpl': output_path,
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            },
            {
                'format': 'best[height<=1080]',
                'outtmpl': output_path,
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1',
            },
            {
                'format': 'best',
                'outtmpl': output_path,
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
            }
        ]
        
        for i, method_opts in enumerate(tiktok_methods):
            try:
                logger.info(f"Trying TikTok extraction method {i+1}...")
                with yt_dlp.YoutubeDL(method_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    for file in os.listdir(temp_dir):
                        if file.startswith('video'):
                            actual_path = os.path.join(temp_dir, file)
                            return actual_path, info.get('title', 'Video')
            except Exception as e:
                logger.error(f"TikTok method {i+1} failed: {e}")
                continue
        
        return None, "All TikTok extraction methods failed"
        
    else:
        instagram_methods = [
            {
                'format': 'best[height<=1080]',
                'outtmpl': output_path,
                'quiet': True,
                'no_warnings': True,
            },
            {
                'format': 'best',
                'outtmpl': output_path,
                'quiet': True,
                'no_warnings': True,
            },
            {
                'format': 'best[ext=mp4]',
                'outtmpl': output_path,
                'quiet': True,
                'no_warnings': True,
            }
        ]
        
        for i, method_opts in enumerate(instagram_methods):
            try:
                logger.info(f"Trying Instagram extraction method {i+1}...")
                with yt_dlp.YoutubeDL(method_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    for file in os.listdir(temp_dir):
                        if file.startswith('video'):
                            actual_path = os.path.join(temp_dir, file)
                            return actual_path, info.get('title', 'Video')
            except Exception as e:
                logger.error(f"Instagram method {i+1} failed: {e}")
                continue
        
        return None, "All Instagram extraction methods failed"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    track_user(user.id, user.username, user.first_name)
    
    welcome_text = (
        f"👋 Welcome to @{BOT_USERNAME}!\n\n"
        "📱 Send me a TikTok or Instagram video link and I'll download it without watermarks.\n\n"
        "🔗 Supported platforms:\n"
        "• TikTok\n"
        "• Instagram\n\n"
        "📊 Commands:\n"
        "/stats - View bot statistics\n"
        "/users - View user count\n"
        "/downloads - View download stats\n\n"
        "💡 Just paste the link and I'll handle the rest!"
    )
    await update.message.reply_text(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 How to use:\n\n"
        "1️⃣ Copy a TikTok or Instagram video link\n"
        "2️⃣ Send it to me\n"
        "3️⃣ I'll download and send the video back\n\n"
        "�� Analytics Commands:\n"
        "/stats - View comprehensive statistics\n"
        "/users - View user information\n"
        "/downloads - View download counts\n\n"
        "⚠️ Note: Videos must be under 50MB due to Telegram limits\n"
        "�� Quality: Up to 1080p\n\n"
        "❓ Need help? Contact the developer"
    )
    await update.message.reply_text(help_text)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = get_stats()
    
    stats_text = (
        "�� **Bot Statistics**\n\n"
        f"�� **Total Users**: {stats['total_users']}\n"
        f"📥 **Total Downloads**: {stats['total_downloads']}\n"
        f"�� **TikTok Downloads**: {stats['tiktok_downloads']}\n"
        f"📸 **Instagram Downloads**: {stats['instagram_downloads']}\n\n"
        f"📅 **Today's Downloads**: {stats['today_downloads']}\n"
        f"📆 **This Month's Downloads**: {stats['month_downloads']}\n\n"
        f"🎯 **Success Rate**: {((stats['total_downloads'] / max(stats['total_users'], 1)) * 100):.1f}%"
    )
    
    await update.message.reply_text(stats_text, parse_mode='Markdown')

async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_analytics()
    total_users = len(data["users"])
    
    users_text = (
        f"👥 **User Statistics**\n\n"
        f"�� **Total Users**: {total_users}\n\n"
        "�� **Recent Users**:\n"
    )
    
    recent_users = list(data["users"].values())[-5:]
    for user in recent_users:
        username = user.get("username", "No username")
        first_name = user.get("first_name", "Unknown")
        last_seen = user.get("last_seen", "Unknown")
        users_text += f"• @{username} ({first_name}) - {last_seen}\n"
    
    await update.message.reply_text(users_text, parse_mode='Markdown')

async def downloads_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = get_stats()
    
    downloads_text = (
        "📥 **Download Statistics**\n\n"
        f"🎯 **Total Downloads**: {stats['total_downloads']}\n"
        f"�� **TikTok**: {stats['tiktok_downloads']}\n"
        f"📸 **Instagram**: {stats['instagram_downloads']}\n\n"
        f"📅 **Today**: {stats['today_downloads']}\n"
        f"📆 **This Month**: {stats['month_downloads']}\n\n"
        "📈 **Platform Distribution**:\n"
    )
    
    if stats['total_downloads'] > 0:
        tiktok_percent = (stats['tiktok_downloads'] / stats['total_downloads']) * 100
        instagram_percent = (stats['instagram_downloads'] / stats['total_downloads']) * 100
        downloads_text += f"• TikTok: {tiktok_percent:.1f}%\n"
        downloads_text += f"• Instagram: {instagram_percent:.1f}%"
    else:
        downloads_text += "• No downloads yet"
    
    await update.message.reply_text(downloads_text, parse_mode='Markdown')

async def handle_video_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    track_user(user.id, user.username, user.first_name)
    
    url = update.message.text.strip()
    
    if not (is_tiktok_url(url) or is_instagram_url(url)):
        await update.message.reply_text(
            "❌ Please send a valid TikTok or Instagram video link."
        )
        return
    
    processing_msg = await update.message.reply_text(
        "⏳ Processing your video... This may take a moment."
    )
    
    try:
        platform = "tiktok" if is_tiktok_url(url) else "instagram"
        
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as executor:
            video_path, title = await loop.run_in_executor(
                executor, download_video, url, platform
            )
        
        if not video_path or not os.path.exists(video_path):
            await processing_msg.edit_text(f"❌ Failed to download video: {title}")
            return
        
        file_size = os.path.getsize(video_path)
        if file_size > MAX_FILE_SIZE:
            await processing_msg.edit_text(
                "❌ Video is too large (>50MB). Telegram has file size limits."
            )
            return
        
        with open(video_path, 'rb') as video_file:
            await context.bot.send_video(
                chat_id=update.effective_chat.id,
                video=video_file,
                caption=f"✅ Downloaded from {platform.title()}\n�� @{BOT_USERNAME}",
                supports_streaming=True
            )
        
        track_download(platform)
        await processing_msg.edit_text("✅ Video sent successfully!")
        
        os.remove(video_path)
        os.rmdir(os.path.dirname(video_path))
        
    except Exception as e:
        logger.error(f"Error processing video: {e}")
        await processing_msg.edit_text(
            "❌ An error occurred while processing the video. Please try again later."
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
    if update and update.message:
        await update.message.reply_text(
            "❌ An unexpected error occurred. Please try again later."
        )

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("users", users_command))
    application.add_handler(CommandHandler("downloads", downloads_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_video_link))
    
    application.add_error_handler(error_handler)
    
    print(f"🤖 Starting @{BOT_USERNAME}...")
    print("📱 Bot is running. Press Ctrl+C to stop.")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()