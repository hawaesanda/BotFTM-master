import os
import logging
from dotenv import load_dotenv
from telegram import Update, BotCommand
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters
)

# 📦 Import semua handler modular
from handler.base_command import register_handler as base_handler
from handler.ceksto_command import register_handler as ceksto_handler
from handler.inputftm_command import register_handler as inputftm_handler
from handler.inputmetro_command import register_handler as inputmetro_handler
from handler.cekgpon_command_v2 import register_handler as cekgpon_handler_v2
from handler.cekmetro_command import register_handler as cekmetro_handler

# Import show handler (setelah file dibuat)
try:
    from handler.show_ftm_command import register_handler as show_ftm_handler
    SHOW_FTM_AVAILABLE = True
except ImportError:
    SHOW_FTM_AVAILABLE = False

# 🔐 Load token dari .env
load_dotenv()
bot_token = os.getenv('BOT_TOKEN')
app = Application.builder().token(bot_token).build()

# 📌 Registrasi semua handler modular
base_handler(app)            # start, cancel, adduser, removeuser, listuser, promote, dismiss
ceksto_handler(app)
inputftm_handler(app)
inputmetro_handler(app)
cekgpon_handler_v2(app)
cekmetro_handler(app)

# Register show handler jika tersedia
if SHOW_FTM_AVAILABLE:
    show_ftm_handler(app)

# 📋 Set command menu Telegram (agar muncul di menu /)
async def set_bot_commands(application):
    commands = [
        BotCommand("start", "Memulai bot"),
        BotCommand("end", "Mengakhiri sesi"),
        BotCommand("register", "Registrasi user baru"),
        BotCommand("removeuser", "Hapus user"),
        BotCommand("listuser", "Lihat daftar user"),
        BotCommand("promote", "Jadikan admin"),
        BotCommand("dismiss", "Turunkan admin"),
        BotCommand("cekgpon", "Cek data GPON"),
        BotCommand("ceksto", "Cek status STO"),
        BotCommand("cekmetro", "Cek data Metro"),
        BotCommand("infosto", "Informasi STO (Metro)"),
        BotCommand("showftm", "Tampilkan data FTM"),
        BotCommand("showgpon", "Tampilkan data per GPON"),
        BotCommand("showsto", "Tampilkan data per STO"),
        BotCommand("inputftm", "Upload data FTM"),
        BotCommand("inputmetro", "Upload data Metro"),
    ]
    await application.bot.set_my_commands(commands)

app.post_init = lambda application: set_bot_commands(application)

# 📍 Handler fallback untuk command tidak dikenal
async def unknown_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"❌ Perintah `{update.message.text}` tidak dikenali.\n"
        "Gunakan menu `/` untuk melihat daftar perintah.",
        parse_mode='Markdown'
    )

# 📍 Handler fallback untuk pesan teks biasa di luar percakapan
async def unknown_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚠️ Maaf, saya tidak mengenali pesan ini.\n"
        "Gunakan menu `/` untuk melihat perintah yang tersedia."
    )

# 📌 Handler fallback selalu diletakkan paling bawah!
app.add_handler(MessageHandler(filters.COMMAND, unknown_command_handler))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_message_handler))

# 🪵 Logging aktivitas
logging.basicConfig(level=logging.INFO)

# ▶️ Jalankan bot
if __name__ == "__main__":
    print('🤖 Bot running...')
    app.run_polling()
