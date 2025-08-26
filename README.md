# TikTok & Instagram Video Downloader Bot

A Telegram bot that downloads videos from TikTok and Instagram without watermarks.

## Features

- ✅ Downloads TikTok videos without watermarks
- ✅ Downloads Instagram videos 
- ✅ Quality up to 1080p
- ✅ File size limit: 50MB (Telegram limit)
- ✅ No cooldown/rate limiting
- ✅ Error handling for invalid links and private content

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Run Locally

```bash
python bot.py
```

The bot will start and respond to messages.

### 3. Test the Bot

1. Open Telegram and search for `@eyysavebot`
2. Send `/start` to get welcome message
3. Send a TikTok or Instagram video link
4. Wait for the bot to download and send the video back

## Free Hosting Options

### Option 1: Railway (Recommended)
1. Go to [railway.app](https://railway.app)
2. Sign up with GitHub
3. Create new project
4. Connect your GitHub repo
5. Deploy automatically

### Option 2: Render
1. Go to [render.com](https://render.com)
2. Sign up and create new Web Service
3. Connect your GitHub repo
4. Set build command: `pip install -r requirements.txt`
5. Set start command: `python bot.py`

### Option 3: Local Machine
- Run `python bot.py` in your terminal
- Keep the terminal open 24/7

## Commands

- `/start` - Welcome message and instructions
- `/help` - Help and usage information
- Send any TikTok/Instagram link to download

## Bot Configuration

- **Token**: Already configured in the code
- **Username**: @eyysavebot
- **Max Quality**: 1080p
- **File Size Limit**: 50MB

## Troubleshooting

- **Bot not responding**: Check if the script is running
- **Download fails**: Link might be private or invalid
- **File too large**: Video exceeds 50MB limit
- **Hosting issues**: Check logs in your hosting platform

## Security Notes

- Bot token is already in the code (ready to run)
- No additional API keys needed
- Uses yt-dlp for safe video downloading

## Support

If you encounter issues:
1. Check the console/logs for error messages
2. Ensure all dependencies are installed
3. Verify the bot token is correct
4. Test with a simple TikTok/Instagram link first
