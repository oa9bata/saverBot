import logging
import re
import os
import tempfile
import asyncio
import concurrent.futures
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp
import subprocess
import shutil

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

def convert_to_telegram_format(input_path: str, output_path: str) -> bool:
    """Convert video to Telegram-optimized format using ffmpeg"""
    try:
        # Check if ffmpeg is available
        if not shutil.which('ffmpeg'):
            logger.warning("ffmpeg not found, skipping conversion")
            return False
        
        # Telegram-optimized encoding settings
        # H.264 codec with baseline profile for better mobile compatibility
        cmd = [
            'ffmpeg',
            '-i', input_path,
            '-c:v', 'libx264',           # H.264 codec
            '-profile:v', 'baseline',     # Baseline profile for mobile compatibility
            '-level', '3.1',              # Level 3.1 for broad compatibility
            '-preset', 'slow',            # Better compression
            '-crf', '23',                 # Quality setting (lower = better quality)
            '-pix_fmt', 'yuv420p',        # Pixel format for compatibility
            '-c:a', 'aac',                # AAC audio codec
            '-b:a', '128k',               # Audio bitrate
            '-movflags', '+faststart',    # Enable progressive download
            '-max_muxing_queue_size', '1024',  # Prevent muxing issues
            '-y',                         # Overwrite output
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        if result.returncode == 0:
            logger.info("Video successfully converted to Telegram format")
            return True
        else:
            logger.error(f"ffmpeg conversion failed: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg conversion timed out")
        return False
    except Exception as e:
        logger.error(f"Error during video conversion: {e}")
        return False

def download_video(url: str, platform: str) -> tuple[str, str]:
    temp_dir = tempfile.mkdtemp()
    raw_output = os.path.join(temp_dir, f"raw_video.{platform}")
    final_output = os.path.join(temp_dir, f"video.mp4")
    
    # Enhanced yt-dlp options for better compatibility
    base_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'socket_timeout': 30,
        'retries': 3,
        'fragment_retries': 3,
        'concurrent_fragment_downloads': 4,
        'http_chunk_size': 10485760,  # 10MB chunks
    }
    
    if platform == "tiktok":
        tiktok_methods = [
            {
                **base_opts,
                'format': 'best[height<=1080][ext=mp4]/best[height<=1080]/best',
                'outtmpl': raw_output,
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'extractor_args': {'tiktok': {'api_hostname': 'api16-normal-c-useast1a.tiktokv.com'}},
            },
            {
                **base_opts,
                'format': 'best[ext=mp4]/best',
                'outtmpl': raw_output,
                'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
            },
            {
                **base_opts,
                'format': 'best',
                'outtmpl': raw_output,
                'cookiesfrombrowser': 'chrome',  # Try using browser cookies
            }
        ]
        
        for i, method_opts in enumerate(tiktok_methods, 1):
            try:
                logger.info(f"Trying TikTok extraction method {i}...")
                with yt_dlp.YoutubeDL(method_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    
                    # Find the downloaded file
                    for file in os.listdir(temp_dir):
                        if file.startswith('raw_video'):
                            actual_path = os.path.join(temp_dir, file)
                            
                            # Convert to Telegram-optimized format
                            if convert_to_telegram_format(actual_path, final_output):
                                os.remove(actual_path)
                                return final_output, info.get('title', 'Video')
                            else:
                                # If conversion fails, return original
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
                'format': 'best[ext=mp4][height<=1080]/best[ext=mp4]/best',
                'outtmpl': raw_output,
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'http_headers': {
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Upgrade-Insecure-Requests': '1',
                },
                'cookiesfrombrowser': 'chrome',  # Try using browser cookies
            },
            {
                **base_opts,
                'format': 'best[height<=720]/best',
                'outtmpl': raw_output,
                'user_agent': 'Instagram 255.0.0.19.120 Android (30/11; 420dpi; 1080x2220; samsung; SM-G973F; beyond1; exynos9820)',
            },
            {
                **base_opts,
                'format': 'best',
                'outtmpl': raw_output,
                'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
                'extractor_args': {'instagram': {'use_api': True}},
            }
        ]
        
        for i, method_opts in enumerate(instagram_methods, 1):
            try:
                logger.info(f"Trying Instagram extraction method {i}...")
                with yt_dlp.YoutubeDL(method_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    
                    # Find the downloaded file
                    for file in os.listdir(temp_dir):
                        if file.startswith('raw_video'):
                            actual_path = os.path.join(temp_dir, file)
                            
                            # Convert to Telegram-optimized format
                            if convert_to_telegram_format(actual_path, final_output):
                                os.remove(actual_path)
                                return final_output, info.get('title', 'Video')
                            else:
                                # If conversion fails, return original
                                return actual_path, info.get('title', 'Video')
                                
            except Exception as e:
                logger.error(f"Instagram method {i} failed: {e}")
                if i == len(instagram_methods):
                    # Provide more helpful error message for Instagram
                    if "login" in str(e).lower() or "private" in str(e).lower():
                        return None, "This Instagram video is private or requires login. Please make sure the video is public."
                    else:
                        return None, f"Failed to download Instagram video. Instagram may be blocking automated downloads. Try again later or use a different video."
                continue
    
    return None, "Failed to download video"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        f"👋 Welcome to @{BOT_USERNAME}!\n\n"
        "📱 Send me a TikTok or Instagram video link and I'll download it without watermarks.\n\n"
        "🔗 Supported platforms:\n"
        "• TikTok (including vm.tiktok.com links)\n"
        "• Instagram (public videos only)\n\n"
        "⚡ Videos are optimized for smooth playback on all devices\n\n"
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
        "• Quality: Up to 1080p\n"
        "• Videos are optimized for smooth playback\n\n"
        "🔧 Troubleshooting:\n"
        "• If video is laggy, try downloading and re-uploading\n"
        "• Instagram may block some downloads temporarily\n\n"
        "❓ Need help? Contact the developer"
    )
    await update.message.reply_text(help_text)

async def handle_video_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    
    # Clean up the URL
    url = url.split('?')[0] if '?' in url else url
    
    if not (is_tiktok_url(url) or is_instagram_url(url)):
        await update.message.reply_text(
            "❌ Please send a valid TikTok or Instagram video link.\n\n"
            "Supported formats:\n"
            "• tiktok.com/@username/video/...\n"
            "• vm.tiktok.com/...\n"
            "• instagram.com/p/... or /reel/...\n"
            "• instagr.am/..."
        )
        return
    
    processing_msg = await update.message.reply_text(
        "⏳ Processing your video...\n"
        "This may take 15-30 seconds depending on the video size."
    )
    
    try:
        platform = "tiktok" if is_tiktok_url(url) else "instagram"
        
        # Update message to show platform
        await processing_msg.edit_text(
            f"⏳ Downloading from {platform.title()}...\n"
            f"Please wait..."
        )
        
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as executor:
            video_path, title = await loop.run_in_executor(
                executor, download_video, url, platform
            )
        
        if not video_path or not os.path.exists(video_path):
            error_msg = title if title else "Unknown error occurred"
            await processing_msg.edit_text(f"❌ {error_msg}")
            return
        
        file_size = os.path.getsize(video_path)
        if file_size > MAX_FILE_SIZE:
            await processing_msg.edit_text(
                f"❌ Video is too large ({file_size / 1024 / 1024:.1f}MB > 50MB).\n"
                "Telegram has file size limits."
            )
            # Clean up
            os.remove(video_path)
            os.rmdir(os.path.dirname(video_path))
            return
        
        # Update message before sending
        await processing_msg.edit_text("📤 Uploading video to Telegram...")
        
        with open(video_path, 'rb') as video_file:
            await context.bot.send_video(
                chat_id=update.effective_chat.id,
                video=video_file,
                caption=f"✅ Downloaded from {platform.title()}\n"
                        f"📱 Optimized for smooth playback\n"
                        f"🤖 @{BOT_USERNAME}",
                supports_streaming=True,
                width=1920,  # Hint for Telegram about video dimensions
                height=1080,
                duration=None,  # Let Telegram figure it out
                disable_notification=False
            )
        
        await processing_msg.delete()  # Delete processing message after success
        
        # Clean up temporary files
        os.remove(video_path)
        os.rmdir(os.path.dirname(video_path))
        
    except Exception as e:
        logger.error(f"Error processing video: {e}")
        await processing_msg.edit_text(
            "❌ An error occurred while processing the video.\n"
            "Please try again later or try a different video."
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
    if update and update.message:
        await update.message.reply_text(
            "❌ An unexpected error occurred. Please try again later."
        )

def main():
    # Check for ffmpeg availability
    if shutil.which('ffmpeg'):
        logger.info("✅ ffmpeg found - video optimization enabled")
    else:
        logger.warning("⚠️ ffmpeg not found - videos won't be optimized for mobile playback")
        logger.warning("Install ffmpeg for better mobile video playback: sudo apt-get install ffmpeg")
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_video_link))
    
    application.add_error_handler(error_handler)
    
    print(f"🤖 Starting @{BOT_USERNAME}...")
    print("📱 Bot is running. Press Ctrl+C to stop.")
    print("💡 Tip: Install ffmpeg for better mobile video playback")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()