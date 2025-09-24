from telegram import Update
from telegram.ext import CommandHandler, ContextTypes, ConversationHandler
from handler.access_control import (
    is_authorized, is_admin, add_allowed_user, remove_allowed_user,
    promote_user, dismiss_user, get_all_allowed_users
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    telegram_id = str(user.id)
    users = get_all_allowed_users()

    if not users:
        # Jika belum ada user sama sekali → jadikan admin pertama
        name = user.full_name
        nik = telegram_id  # bisa diubah nanti oleh admin
        add_allowed_user(name, nik, telegram_id, role="admin")
        await update.message.reply_text(
            f"👑 Kamu adalah pengguna pertama. Ditambahkan sebagai *admin* otomatis.\n",
            parse_mode="Markdown"
        )
        return

    if not is_authorized(telegram_id):
        await update.message.reply_text("❌ Maaf, Anda tidak memiliki izin untuk menggunakan bot ini.")
        return

    await update.message.reply_text(
        f"Halo {user.first_name}! Bot siap untuk digunakan.\n"
        "Gunakan menu `/` di bawah untuk melihat perintah yang tersedia."
    )


# /end
async def end(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_authorized(str(user.id)):
        await update.message.reply_text("❌ Maaf, Anda tidak memiliki izin.")
        return
    await update.message.reply_text("✅ Sesi kamu telah diakhiri.")


# /cancel
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not is_authorized(str(user.id)):
        await update.message.reply_text("❌ Maaf, Anda tidak memiliki izin.")
        return ConversationHandler.END
    await update.message.reply_text("❌ Proses dibatalkan.")
    return ConversationHandler.END

# /removeuser TELEGRAM_ID
async def removeuser(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    admin = update.effective_user
    admin_id = str(admin.id)

    if not is_admin(admin_id):
        await update.message.reply_text("❌ Kamu tidak memiliki izin untuk menghapus user.")
        return

    if len(context.args) < 1:
        await update.message.reply_text("⚠️ Gunakan format: `/removeuser TELEGRAM_ID`", parse_mode="Markdown")
        return

    target_id = context.args[0]

    if target_id == admin_id:
        await update.message.reply_text("⚠️ Kamu tidak bisa menghapus dirimu sendiri.")
        return

    if remove_allowed_user(target_id):
        await update.message.reply_text(f"✅ Telegram ID {target_id} berhasil dihapus.")
    else:
        await update.message.reply_text("ℹ️ User tidak ditemukan.")


# ⬆/promote
async def promote(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    admin = update.effective_user
    if not is_admin(str(admin.id)):
        await update.message.reply_text("❌ Kamu tidak memiliki izin untuk promote user.")
        return

    if len(context.args) < 1:
        await update.message.reply_text("⚠️ Gunakan format: `/promote TELEGRAM_ID`", parse_mode="Markdown")
        return

    target_id = context.args[0]

    if promote_user(target_id):
        await update.message.reply_text(f"✅ Telegram ID {target_id} berhasil dijadikan *admin*.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"ℹ️ User tidak ditemukan.")


# ⬇/dismiss
async def dismiss(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    admin = update.effective_user
    if not is_admin(str(admin.id)):
        await update.message.reply_text("❌ Kamu tidak memiliki izin untuk dismiss admin.")
        return

    if len(context.args) < 1:
        await update.message.reply_text("⚠️ Gunakan format: `/dismiss TELEGRAM_ID`", parse_mode="Markdown")
        return

    target_id = context.args[0]

    if dismiss_user(target_id):
        await update.message.reply_text(f"✅ Telegram ID {target_id} berhasil diturunkan menjadi *user*.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"ℹ️ User tidak ditemukan.")


# /listuser
async def listuser(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    admin = update.effective_user
    if not is_admin(str(admin.id)):
        await update.message.reply_text("❌ Hanya admin yang dapat melihat daftar pengguna.")
        return

    users = get_all_allowed_users()
    if not users:
        await update.message.reply_text("📭 Daftar pengguna kosong.")
        return

    daftar = "\n".join([
        f"- {u['name']} ({u['nik']}) [@{u['telegram_id']}] - {u['role']}"
        for u in users
    ])
    await update.message.reply_text(f"📋 *Daftar Pengguna:*\n\n{daftar}", parse_mode="Markdown")

# /register "Nama Lengkap" NIK
async def register(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    telegram_id = str(user.id)

    if is_authorized(telegram_id):
        await update.message.reply_text("✅ Kamu sudah terdaftar.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Gunakan format: `/register \"Nama Lengkap\" NIK`", parse_mode="Markdown")
        return

    name = " ".join(context.args[:-1]).strip('"')
    nik = context.args[-1]

    if add_allowed_user(name, nik, telegram_id, role="user"):
        await update.message.reply_text(f"✅ Registrasi berhasil. Selamat datang, *{name}*!", parse_mode="Markdown")
    else:
        await update.message.reply_text("⚠️ Gagal menambahkan. Mungkin kamu sudah terdaftar.")

# 📌 Register semua handler
def register_handler(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("end", end))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("removeuser", removeuser))
    app.add_handler(CommandHandler("listuser", listuser))
    app.add_handler(CommandHandler("promote", promote))
    app.add_handler(CommandHandler("dismiss", dismiss))
    app.add_handler(CommandHandler("register", register))

