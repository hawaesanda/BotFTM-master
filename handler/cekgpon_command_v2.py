import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    CallbackContext,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from telegram.constants import ParseMode
from database import get_connection_database
from handler.base_command import cancel, start
from handler.access_control import is_authorized  # <-- pakai auth JSON

logging.basicConfig(level=logging.INFO)

ASK_WITEL, ASK_STO, ASK_GPON, ASK_CARD = range(4)

WITEL_TABLE_MAP = {
    "Malang": "ftm_data_mlg",
    "Madiun": "ftm_data_mdn",
    "Kediri": "ftm_data_kdr",
}

async def _auth_guard(update: Update, _: CallbackContext) -> bool:
    """Blokir akses jika telegram_id belum terdaftar di allowed_users.json."""
    user = update.effective_user
    telegram_id = str(user.id) if user else ""
    if is_authorized(telegram_id):
        return True

    if update.callback_query:
        q = update.callback_query
        # munculkan alert pop-up
        await q.answer("Akses ditolak: kamu belum terdaftar sebagai user.", show_alert=True)
        try:
            await q.message.reply_text(
                "❌ *Akses ditolak*\n"
                "Anda belum terdaftar di sistem. Silakan register terlebih dahulu.",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception:
            pass
    else:
        if update.message:
            await update.message.reply_text(
                "❌ *Akses ditolak*\n"
                "Anda belum terdaftar di sistem. Silakan register terlebih dahulu.",
                parse_mode=ParseMode.MARKDOWN,
            )
    return False

async def start_cekgpon(update: Update, context: CallbackContext) -> int:
    if not await _auth_guard(update, context):
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("Malang", callback_data="Malang")],
        [InlineKeyboardButton("Madiun", callback_data="Madiun")],
        [InlineKeyboardButton("Kediri", callback_data="Kediri")],
    ]
    await update.message.reply_text(
        "📍 Silakan pilih *Witel* terlebih dahulu:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return ASK_WITEL

async def handle_witel_selection(update: Update, context: CallbackContext) -> int:
    if not await _auth_guard(update, context):
        return ConversationHandler.END

    query = update.callback_query
    await query.answer()
    witel = query.data
    context.user_data["witel"] = witel
    table_name = WITEL_TABLE_MAP.get(witel)

    try:
        conn = get_connection_database()
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT DISTINCT sto FROM {table_name}
                WHERE LOWER(witel) = LOWER(%s)
                ORDER BY sto
                """,
                (witel,)
            )
            sto_result = cursor.fetchall()
            sto_list = [row["sto"] for row in sto_result if row["sto"]]
    except Exception as e:
        logging.error(f"Gagal ambil daftar STO: {e}")
        await query.message.reply_text("❌ Gagal mengambil daftar STO dari database.")
        return ConversationHandler.END
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if sto_list:
        buttons = []
        for i in range(0, len(sto_list), 3):
            row_buttons = [
                InlineKeyboardButton(sto, callback_data=f"STO_{sto}")
                for sto in sto_list[i:i+3]
            ]
            buttons.append(row_buttons)

        await query.message.reply_text(
            f"✅ Witel *{witel}* dipilih.\n\nSilakan pilih *STO* yang tersedia:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return ASK_STO
    else:
        await query.message.reply_text(
            f"✅ Witel *{witel}* dipilih.\nNamun tidak ditemukan STO.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

async def handle_sto_selection(update: Update, context: CallbackContext) -> int:
    if not await _auth_guard(update, context):
        return ConversationHandler.END

    query = update.callback_query
    await query.answer()

    sto_selected = query.data.replace("STO_", "")
    context.user_data["nama_sto"] = sto_selected

    witel = context.user_data.get("witel")
    table_name = WITEL_TABLE_MAP.get(witel)

    try:
        conn = get_connection_database()
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT DISTINCT nama_gpon FROM {table_name}
                WHERE LOWER(witel) = LOWER(%s) AND LOWER(sto) = LOWER(%s)
                """,
                (witel, sto_selected),
            )
            results = cursor.fetchall()

        gpon_list = [row["nama_gpon"] for row in results if row["nama_gpon"]]
        unique_gpon = sorted(set(gpon_list))

        if unique_gpon:
            context.user_data["gpon_list"] = unique_gpon
            context.user_data["gpon_page"] = 0
            await show_gpon_page(update, context, use_message=False)
            return ASK_GPON
        else:
            await query.edit_message_text(
                f"❌ Tidak ada *GPON* ditemukan untuk STO {sto_selected}.",
                parse_mode="Markdown"
            )
            return ConversationHandler.END

    except Exception as e:
        logging.error(f"DB Error: {e}")
        await query.edit_message_text("❌ Terjadi kesalahan saat mengambil data dari database.")
        return ConversationHandler.END
    finally:
        try:
            conn.close()
        except Exception:
            pass

async def show_gpon_page(update: Update, context: CallbackContext, use_message=True):
    # Fungsi ini dipanggil dari handler yang sudah lewat _auth_guard
    gpons = context.user_data.get("gpon_list", [])
    page = context.user_data.get("gpon_page", 0)
    per_page = 9

    total_pages = (len(gpons) + per_page - 1) // per_page or 1
    # amankan indeks halaman
    page = max(0, min(page, total_pages - 1))
    context.user_data["gpon_page"] = page

    start = page * per_page
    end = start + per_page
    current_page = gpons[start:end]

    buttons = []
    for i in range(0, len(current_page), 3):
        row = [
            InlineKeyboardButton(gpon, callback_data=f"GPON_{gpon}")
            for gpon in current_page[i:i+3]
        ]
        buttons.append(row)

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Sebelumnya", callback_data="prev_gpon"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("➡️ Berikutnya", callback_data="next_gpon"))
    if nav_buttons:
        buttons.append(nav_buttons)

    msg = f"*Pilih GPON* _(halaman {page+1}/{total_pages})_ untuk STO *{context.user_data.get('nama_sto')}*:"
    markup = InlineKeyboardMarkup(buttons)

    if use_message and update.message:
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=markup)
    else:
        await update.callback_query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=markup)

async def handle_pagination(update: Update, context: CallbackContext) -> int:
    if not await _auth_guard(update, context):
        return ConversationHandler.END

    query = update.callback_query
    await query.answer()

    if query.data == "next_gpon":
        context.user_data["gpon_page"] = context.user_data.get("gpon_page", 0) + 1
    elif query.data == "prev_gpon":
        context.user_data["gpon_page"] = context.user_data.get("gpon_page", 0) - 1

    await show_gpon_page(update, context, use_message=False)
    return ASK_GPON

async def handle_gpon_selection(update: Update, context: CallbackContext) -> int:
    if not await _auth_guard(update, context):
        return ConversationHandler.END

    query = update.callback_query
    await query.answer()
    selected_gpon = query.data.replace("GPON_", "")
    context.user_data["nama_gpon"] = selected_gpon

    await query.message.reply_text(
        "Silakan masukkan Nomor Slot/Port dalam format `card/port`.\n\nContoh: `1/1`",
        parse_mode="Markdown"
    )
    return ASK_CARD

async def main_cekgpon(update: Update, context: CallbackContext) -> int:
    if not await _auth_guard(update, context):
        return ConversationHandler.END

    witel = context.user_data.get("witel")
    nama_sto = context.user_data.get("nama_sto")
    nama_gpon = context.user_data.get("nama_gpon")
    slot_input = update.message.text.strip()
    table_name = WITEL_TABLE_MAP.get(witel)

    if not table_name:
        await update.message.reply_text("❌ Witel tidak dikenali.")
        return ConversationHandler.END

    try:
        card_number, port_number = slot_input.split("/")
        card_number = int(card_number.strip())
        port_number = int(port_number.strip())
    except ValueError:
        await update.message.reply_text(
            "❌ Format salah. Gunakan format `card/port`.\nContoh: `3/4`",
            parse_mode="Markdown"
        )
        return ASK_CARD

    try:
        conn = get_connection_database()
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT * FROM {table_name}
                WHERE LOWER(witel) = LOWER(%s)
                AND LOWER(sto) = LOWER(%s)
                AND LOWER(nama_gpon) = LOWER(%s)
                AND card = %s AND port = %s
                """,
                (witel, nama_sto, nama_gpon, card_number, port_number)
            )
            results = cursor.fetchall()

        if results:
            for gpon_data in results:
                result_text = f"""
✅ *Data GPON Ditemukan!*
📌 *Witel:* {gpon_data["witel"]}
🏢 *STO:* {gpon_data["sto"]}
🛜 *IP:* {gpon_data["ip"]}
🔢 *Nama GPON:* {gpon_data["nama_gpon"]}
🛠 *Card:* {gpon_data["card"]}
🔌 *Port:* {gpon_data["port"]}

📡 *Lemari FTM Eakses:* {gpon_data["nama_lemari_ftm_eakses"]}
🎛 *Panel Eakses:* {gpon_data["no_panel_eakses"]} (Port {gpon_data["no_port_panel_eakses"]})

🟢 *Status Feeder:* {gpon_data["status_feeder"]}
🔗 *Nama Feeder:* {gpon_data["nama_segmen_feeder_utama"]}

🏢 *ODC:* {gpon_data["nama_odc"]}
"""
                await update.message.reply_text(result_text, parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ Data tidak ditemukan untuk input tersebut.")

    except Exception as e:
        logging.error(f"Query error: {e}")
        await update.message.reply_text("❌ Terjadi kesalahan saat mengambil data dari database.")
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return ConversationHandler.END

def register_handler(rh):
    print("✅ cekgpon handler registered")
    handler = ConversationHandler(
        entry_points=[CommandHandler("cekgpon", start_cekgpon)],
        states={
            ASK_WITEL: [CallbackQueryHandler(handle_witel_selection)],
            ASK_STO: [CallbackQueryHandler(handle_sto_selection, pattern="^STO_")],
            ASK_GPON: [
                CallbackQueryHandler(handle_pagination, pattern="^(next_gpon|prev_gpon)$"),
                CallbackQueryHandler(handle_gpon_selection, pattern="^GPON_"),
            ],
            ASK_CARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, main_cekgpon)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),      
            CommandHandler("cekgpon", start_cekgpon)
        ],
        allow_reentry=True
    )
    rh.add_handler(handler)
