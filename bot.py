import logging
import re
import os
import tempfile
import asyncio
import concurrent.futures
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp
import json
from datetime import datetime

class UsageTracker:
    def __init__(self, file_path="usage_data.json"):
        self.file_path = file_path
        
    def get_current_month_key(self):
        return datetime.now().strftime("%Y-%m")
    
    def load_data(self):
        try:
            with open(self.file_path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
    
    def save_data(self, data):
        with open(self.file_path, 'w') as f:
            json.dump(data, f)
    
    def increment_usage(self):
        data = self.load_data()
        month_key = self.get_current_month_key()
        data[month_key] = data.get(month_key, 0) + 1
        self.save_data(data)
    
    def get_monthly_usage(self):
        data = self.load_data()
        month_key = self.get_current_month_key()
        return data.get(month_key, 0)


usage_tracker = UsageTracker()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "default_token")
BOT_USERNAME = "eyysavebot"
MAX_FILE_SIZE = 50 * 1024 * 1024

def is_tiktok_url(url: str) -> bool:
    return 'tiktok.com' in url.lower() or 'vm.tiktok.com' in url.lower()

def is_instagram_url(url: str) -> bool:
    patterns = ['instagram.com', 'instagr.am', 'ig.me']
    return any(pattern in url.lower() for pattern in patterns)

def download_video(url: str, platform: str) -> tuple[str, str]:
    import subprocess
    
    temp_dir = tempfile.mkdtemp()
    raw_path = os.path.join(temp_dir, "raw_video")
    output_path = os.path.join(temp_dir, "video.mp4")
    
    # Simple download first, then process
    base_opts = {
        'outtmpl': raw_path,
        'quiet': True,
        'no_warnings': True,
        'format': 'best[height<=720]/best',
        'socket_timeout': 30,
        'retries': 3,
    }
    
    # Download first
    if platform == "tiktok":
        try:
            with yt_dlp.YoutubeDL(base_opts) as ydl:
                ydl.download([url])
        except Exception as e:
            return None, f"Failed to download: {str(e)}"
    else:  # Instagram  
        try:
            with yt_dlp.YoutubeDL(base_opts) as ydl:
                ydl.download([url])
        except Exception as e:
            return None, "Failed to download Instagram video"
    
    # Find downloaded file
    raw_file = None
    for file in os.listdir(temp_dir):
        if file.startswith('raw_video'):
            raw_file = os.path.join(temp_dir, file)
            break
    
    if not raw_file:
        return None, "Download failed"
    
    # Force mobile-compatible encoding with FFmpeg
    try:
        subprocess.run([
            'ffmpeg', '-i', raw_file, '-y',
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '28',
            '-maxrate', '1500k', '-bufsize', '3000k',
            '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',  # Even dimensions
            '-c:a', 'aac', '-b:a', '96k', '-ar', '44100',
            '-profile:v', 'baseline', '-level', '3.0',
            '-movflags', '+faststart',
            output_path
        ], check=True, capture_output=True)
        
        # Clean up raw file
        os.remove(raw_file)
        return output_path, "Video"
        
    except subprocess.CalledProcessError:
        return None, "Processing failed"
    
    if platform == "tiktok":
        tiktok_methods = [
            {
                **base_opts,
                # Prefer H.264 codec videos from TikTok
                'format': 'best[ext=mp4][vcodec^=avc1][height<=1080]/best[ext=mp4][height<=1080]/best[ext=mp4]/best',
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            },
            {
                **base_opts,
                'format': 'best[ext=mp4]/best',
                'user_agent': 'TikTok 26.1.3 rv:261303 (iPhone; iOS 14.4.2; en_US) Cronet',
            },
            {
                **base_opts,
                'cookiesfrombrowser': 'chrome',
            }
        ]
        
        for i, method_opts in enumerate(tiktok_methods, 1):
            try:
                logger.info(f"Trying TikTok extraction method {i}...")
                with yt_dlp.YoutubeDL(method_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    
                    # Find the downloaded file
                    for file in os.listdir(temp_dir):
                        if file.startswith('video') and (file.endswith('.mp4') or file.endswith('.webm')):
                            actual_path = os.path.join(temp_dir, file)
                            # Log video codec info
                            if info.get('vcodec'):
                                logger.info(f"Downloaded video codec: {info.get('vcodec')}")
                            return actual_path, info.get('title', 'Video')
                            
            except Exception as e:
                logger.error(f"TikTok method {i} failed: {e}")
                if i == len(tiktok_methods):
                    return None, f"Failed to download TikTok video: {str(e)}"
                continue
        
    else:  # Instagram
        instagram_methods = [
            {
                **base_opts,
                # Instagram usually serves H.264 already
                'format': 'best[ext=mp4][vcodec^=avc1][height<=1080]/best[ext=mp4][height<=1080]/best[ext=mp4]/best',
                'user_agent': 'Instagram 276.0.0.15.103 Android (30/11; 420dpi; 1080x2220; samsung; SM-G973F; beyond1; exynos9820)',
                'http_headers': {
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Sec-Fetch-Mode': 'navigate',
                },
            },
            {
                **base_opts,
                'cookiesfrombrowser': 'chrome',
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            },
            {
                **base_opts,
                'format': 'best[height<=720]/best',
                'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15',
            }
        ]
        
        for i, method_opts in enumerate(instagram_methods, 1):
            try:
                logger.info(f"Trying Instagram extraction method {i}...")
                with yt_dlp.YoutubeDL(method_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    
                    # Find the downloaded file
                    for file in os.listdir(temp_dir):
                        if file.startswith('video') and (file.endswith('.mp4') or file.endswith('.webm')):
                            actual_path = os.path.join(temp_dir, file)
                            # Log video codec info
                            if info.get('vcodec'):
                                logger.info(f"Downloaded video codec: {info.get('vcodec')}")
                            return actual_path, info.get('title', 'Video')
                            
            except Exception as e:
                logger.error(f"Instagram method {i} failed: {e}")
                if i == len(instagram_methods):
                    if "login" in str(e).lower() or "private" in str(e).lower():
                        return None, "This Instagram video is private or requires login."
                    else:
                        return None, "Failed to download Instagram video. Try again later."
                continue
    
    return None, "Failed to download video"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    monthly_usage = usage_tracker.get_monthly_usage()
    welcome_text = (
        f"👋 Welcome to @{BOT_USERNAME}!\n"
        f"📊 Monthly downloads: {monthly_usage}\n\n"
        "📱 Send me a TikTok or Instagram video link and I'll download it without watermarks.\n\n"
        "🔗 Supported platforms:\n"
        "• TikTok\n"
        "• Instagram (public videos)\n\n"
        "💡 Just paste the link and I'll handle the rest!"
    )
    await update.message.reply_text(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 How to use:\n\n"
        "1️⃣ Copy a TikTok or Instagram video link\n"
        "2️⃣ Send it to me\n"
        "3️⃣ I'll download and send the video back\n\n"
        "⚠️ Notes:\n"
        "• Videos must be under 50MB\n"
        "• Instagram videos must be public\n"
        "• Quality: Up to 1080p\n\n"
        "❓ Need help? Contact the developer"
    )
    await update.message.reply_text(help_text)

async def handle_video_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            await processing_msg.edit_text(f"❌ {title}")
            return
        
        file_size = os.path.getsize(video_path)
        if file_size > MAX_FILE_SIZE:
            await processing_msg.edit_text(
                f"❌ Video is too large ({file_size / 1024 / 1024:.1f}MB > 50MB)."
            )
            os.remove(video_path)
            os.rmdir(os.path.dirname(video_path))
            return
        
        # Send with optimized settings for mobile
        with open(video_path, 'rb') as video_file:
            await context.bot.send_video(
                chat_id=update.effective_chat.id,
                video=video_file,
                caption=f"✅ Downloaded from {platform.title()}\n🤖 @{BOT_USERNAME}",
                supports_streaming=True,
                width=1280,
                height=720,
                parse_mode=None,
                disable_notification=False
            )
        
        usage_tracker.increment_usage()

        await processing_msg.delete()
        
        # Clean up
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
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_video_link))
    
    application.add_error_handler(error_handler)
    
    print(f"🤖 Starting @{BOT_USERNAME}...")
    print("📱 Bot is running. Press Ctrl+C to stop.")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()