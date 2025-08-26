import logging
import re
import os
import tempfile
import asyncio
import concurrent.futures
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp
import requests

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = os.getenv("BOT_TOKEN", "default_token")
BOT_USERNAME = "eyysavebot"
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB Telegram limit

def is_tiktok_url(url: str) -> bool:
    """Check if URL is TikTok"""
    return 'tiktok.com' in url.lower()

def is_instagram_url(url: str) -> bool:
    """Check if URL is Instagram"""
    return 'instagram.com' in url.lower()

def download_video(url: str, platform: str) -> tuple[str, str]:
    """Download video without watermark"""
    temp_dir = tempfile.mkdtemp()
    output_path = os.path.join(temp_dir, f"video.{platform}")
    
    if platform == "tiktok":
        # Try multiple TikTok extraction methods
        tiktok_methods = [
            # Method 1: Standard with user agent
            {
                'format': 'best[height<=1080]',
                'outtmpl': output_path,
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            },
            # Method 2: Mobile user agent
            {
                'format': 'best[height<=1080]',
                'outtmpl': output_path,
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1',
            },
            # Method 3: Simple format
            {
                'format': 'best',
                'outtmpl': output_path,
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
            }
        ]
        
        # Try each method until one works
        for i, method_opts in enumerate(tiktok_methods):
            try:
                logger.info(f"Trying TikTok extraction method {i+1}...")
                with yt_dlp.YoutubeDL(method_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    # Find the actual downloaded file
                    for file in os.listdir(temp_dir):
                        if file.startswith('video'):
                            actual_path = os.path.join(temp_dir, file)
                            return actual_path, info.get('title', 'Video')
            except Exception as e:
                logger.error(f"TikTok method {i+1} failed: {e}")
                continue
        
        return None, "All TikTok extraction methods failed"
        
    else:  # Instagram
        # Try multiple Instagram extraction methods
        instagram_methods = [
            # Method 1: Best quality with height limit
            {
                'format': 'best[height<=1080]',
                'outtmpl': output_path,
                'quiet': True,
                'no_warnings': True,
            },
            # Method 2: Best available format
            {
                'format': 'best',
                'outtmpl': output_path,
                'quiet': True,
                'no_warnings': True,
            },
            # Method 3: MP4 format specifically
            {
                'format': 'best[ext=mp4]',
                'outtmpl': output_path,
                'quiet': True,
                'no_warnings': True,
            }
        ]
        
        # Try each method until one works
        for i, method_opts in enumerate(instagram_methods):
            try:
                logger.info(f"Trying Instagram extraction method {i+1}...")
                with yt_dlp.YoutubeDL(method_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    # Find the actual downloaded file
                    for file in os.listdir(temp_dir):
                        if file.startswith('video'):
                            actual_path = os.path.join(temp_dir, file)
                            return actual_path, info.get('title', 'Video')
            except Exception as e:
                logger.error(f"Instagram method {i+1} failed: {e}")
                continue
        
        return None, "All Instagram extraction methods failed"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send start message"""
    welcome_text = (
        f"👋 Welcome to @{BOT_USERNAME}!\n\n"
        "📱 Send me a TikTok or Instagram video link and I'll download it without watermarks.\n\n"
        "🔗 Supported platforms:\n"
        "• TikTok\n"
        "• Instagram\n\n"
        "💡 Just paste the link and I'll handle the rest!"
    )
    await update.message.reply_text(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send help message"""
    help_text = (
        "📖 How to use:\n\n"
        "1️⃣ Copy a TikTok or Instagram video link\n"
        "2️⃣ Send it to me\n"
        "3️⃣ I'll download and send the video back\n\n"
        "⚠️ Note: Videos must be under 50MB due to Telegram limits\n"
        "🎯 Quality: Up to 1080p\n\n"
        "❓ Need help? Contact the developer"
    )
    await update.message.reply_text(help_text)

async def handle_video_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle video link messages"""
    url = update.message.text.strip()
    
    # Check if it's a valid URL
    if not (is_tiktok_url(url) or is_instagram_url(url)):
        await update.message.reply_text(
            "❌ Please send a valid TikTok or Instagram video link."
        )
        return
    
    # Send processing message
    processing_msg = await update.message.reply_text(
        "⏳ Processing your video... This may take a moment."
    )
    
    try:
        # Determine platform
        platform = "tiktok" if is_tiktok_url(url) else "instagram"
        
        # Download video in background thread (non-blocking)
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as executor:
            video_path, title = await loop.run_in_executor(
                executor, download_video, url, platform
            )
        
        if not video_path or not os.path.exists(video_path):
            await processing_msg.edit_text(f"❌ Failed to download video: {title}")
            return
        
        # Check file size
        file_size = os.path.getsize(video_path)
        if file_size > MAX_FILE_SIZE:
            await processing_msg.edit_text(
                "❌ Video is too large (>50MB). Telegram has file size limits."
            )
            return
        
        # Send video
        with open(video_path, 'rb') as video_file:
            await context.bot.send_video(
                chat_id=update.effective_chat.id,
                video=video_file,
                caption=f"✅ Downloaded from {platform.title()}\n📱 @{BOT_USERNAME}",
                supports_streaming=True
            )
        
        await processing_msg.edit_text("✅ Video sent successfully!")
        
        # Clean up
        os.remove(video_path)
        os.rmdir(os.path.dirname(video_path))
        
    except Exception as e:
        logger.error(f"Error processing video: {e}")
        await processing_msg.edit_text(
            "❌ An error occurred while processing the video. Please try again later."
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Update {update} caused error {context.error}")
    if update and update.message:
        await update.message.reply_text(
            "❌ An unexpected error occurred. Please try again later."
        )

def main():
    """Start the bot"""
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_video_link))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Start bot
    print(f"🤖 Starting @{BOT_USERNAME}...")
    print("📱 Bot is running. Press Ctrl+C to stop.")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
