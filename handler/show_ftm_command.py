from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CallbackContext, ConversationHandler, CommandHandler,
    CallbackQueryHandler, MessageHandler, filters
)
from telegram.constants import ParseMode
from database import get_connection_database
from handler.base_command import cancel
from handler.access_control import is_authorized
import logging

ASK_WITEL, ASK_OPTION, ASK_STO, ASK_GPON = range(4)

WITEL_TABLE_MAP = {
    "Malang": "ftm_data_mlg",
    "Madiun": "ftm_data_mdn",
    "Kediri": "ftm_data_kdr",
}

async def _auth_guard(update: Update) -> bool:
    """Cek otentikasi user"""
    user = update.effective_user
    telegram_id = str(user.id) if user else ""
    if is_authorized(telegram_id):
        return True

    if update.callback_query:
        q = update.callback_query
        await q.answer("Akses ditolak: Anda belum terdaftar sebagai user.", show_alert=True)
        try:
            await q.message.reply_text(
                "❌ *Akses ditolak*\nAnda belum terdaftar di sistem. Silakan register terlebih dahulu.",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            pass
    elif update.message:
        await update.message.reply_text(
            "❌ *Akses ditolak*\nAnda belum terdaftar di sistem. Silakan register terlebih dahulu.",
            parse_mode=ParseMode.MARKDOWN
        )
    return False

async def start_showftm(update: Update, context: CallbackContext) -> int:
    """Entry point untuk /showftm"""
    if not await _auth_guard(update):
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("Malang", callback_data="Malang")],
        [InlineKeyboardButton("Madiun", callback_data="Madiun")],
        [InlineKeyboardButton("Kediri", callback_data="Kediri")],
    ]
    await update.message.reply_text(
        "📍 Pilih *Witel* untuk menampilkan data FTM:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return ASK_WITEL

async def handle_witel_selection(update: Update, context: CallbackContext) -> int:
    """Handler untuk pemilihan Witel"""
    if not await _auth_guard(update):
        return ConversationHandler.END

    query = update.callback_query
    await query.answer()
    witel = query.data
    context.user_data["witel"] = witel
    context.user_data["table_name"] = WITEL_TABLE_MAP.get(witel)

    keyboard = [
        [InlineKeyboardButton("📊 Show All FTM Data", callback_data="show_all")],
        [InlineKeyboardButton("🏢 Show per STO", callback_data="show_per_sto")],
        [InlineKeyboardButton("🌐 Show per GPON", callback_data="show_per_gpon")],
    ]
    
    await query.edit_message_text(
        f"✅ Witel *{witel}* dipilih.\n\nPilih opsi tampilan data:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ASK_OPTION

async def handle_option_selection(update: Update, context: CallbackContext) -> int:
    """Handler untuk pemilihan opsi tampilan"""
    if not await _auth_guard(update):
        return ConversationHandler.END

    query = update.callback_query
    await query.answer()
    option = query.data
    context.user_data["option"] = option
    
    witel = context.user_data.get("witel")
    table_name = context.user_data.get("table_name")

    if option == "show_all":
        # Tampilkan semua data FTM untuk witel ini
        await show_all_ftm_data(query, witel, table_name)
        return ConversationHandler.END
        
    elif option == "show_per_sto":
        # Minta pilih STO
        await show_sto_options(query, context, witel, table_name)
        return ASK_STO
        
    elif option == "show_per_gpon":
        # Minta pilih GPON
        await show_gpon_options(query, context, witel, table_name)
        return ASK_GPON

async def show_all_ftm_data(query, witel, table_name):
    """Tampilkan ringkasan semua data FTM"""
    try:
        conn = get_connection_database()
        with conn.cursor() as cursor:
            # Query ringkasan data
            cursor.execute(f"""
                SELECT 
                    COUNT(*) as total_records,
                    COUNT(DISTINCT sto) as total_sto,
                    COUNT(DISTINCT nama_gpon) as total_gpon,
                    COUNT(DISTINCT nama_odc) as total_odc
                FROM {table_name}
                WHERE LOWER(witel) = LOWER(%s)
            """, (witel,))
            summary = cursor.fetchone()
            
            # Query STO list
            cursor.execute(f"""
                SELECT sto, COUNT(*) as count 
                FROM {table_name} 
                WHERE LOWER(witel) = LOWER(%s)
                GROUP BY sto 
                ORDER BY sto
            """, (witel,))
            sto_data = cursor.fetchall()
            
    except Exception as e:
        logging.error(f"Database error: {e}")
        await query.edit_message_text("❌ Gagal mengambil data dari database.")
        return
    finally:
        try:
            conn.close()
        except Exception:
            pass

    # Format pesan ringkasan
    result_text = f"""📊 *Ringkasan Data FTM - {witel}*

📈 *Total Records:* {summary['total_records']}
🏢 *Total STO:* {summary['total_sto']}
🌐 *Total GPON:* {summary['total_gpon']}
🏗 *Total ODC:* {summary['total_odc']}

📋 *Detail per STO:*
"""
    
    for sto in sto_data:
        result_text += f"• {sto['sto']}: {sto['count']} records\n"

    await query.edit_message_text(result_text, parse_mode="Markdown")

async def show_sto_options(query, context, witel, table_name):
    """Tampilkan pilihan STO"""
    try:
        conn = get_connection_database()
        with conn.cursor() as cursor:
            cursor.execute(f"""
                SELECT DISTINCT sto FROM {table_name}
                WHERE LOWER(witel) = LOWER(%s)
                ORDER BY sto
            """, (witel,))
            sto_result = cursor.fetchall()
            sto_list = [row["sto"] for row in sto_result if row["sto"]]
    except Exception as e:
        logging.error(f"Database error: {e}")
        await query.edit_message_text("❌ Gagal mengambil daftar STO.")
        return
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

        await query.edit_message_text(
            f"🏢 Pilih *STO* dari Witel {witel}:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    else:
        await query.edit_message_text("❌ Tidak ditemukan STO.")

async def show_gpon_options(query, context, witel, table_name):
    """Tampilkan pilihan GPON"""
    try:
        conn = get_connection_database()
        with conn.cursor() as cursor:
            cursor.execute(f"""
                SELECT DISTINCT nama_gpon FROM {table_name}
                WHERE LOWER(witel) = LOWER(%s)
                ORDER BY nama_gpon
            """, (witel,))
            gpon_result = cursor.fetchall()
            gpon_list = [row["nama_gpon"] for row in gpon_result if row["nama_gpon"]]
    except Exception as e:
        logging.error(f"Database error: {e}")
        await query.edit_message_text("❌ Gagal mengambil daftar GPON.")
        return
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if gpon_list:
        # Batasi tampilan karena bisa banyak
        limited_gpon = gpon_list[:15]  # Ambil 15 pertama
        buttons = []
        for i in range(0, len(limited_gpon), 3):
            row_buttons = [
                InlineKeyboardButton(gpon, callback_data=f"GPON_{gpon}")
                for gpon in limited_gpon[i:i+3]
            ]
            buttons.append(row_buttons)

        msg = f"🌐 Pilih *GPON* dari Witel {witel}:"
        if len(gpon_list) > 15:
            msg += f"\n\n_Menampilkan 15 dari {len(gpon_list)} GPON tersedia_"

        await query.edit_message_text(
            msg,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    else:
        await query.edit_message_text("❌ Tidak ditemukan GPON.")

async def handle_sto_selection(update: Update, context: CallbackContext) -> int:
    """Handler untuk pemilihan STO"""
    if not await _auth_guard(update):
        return ConversationHandler.END

    query = update.callback_query
    await query.answer()
    sto_selected = query.data.replace("STO_", "")
    
    witel = context.user_data.get("witel")
    table_name = context.user_data.get("table_name")

    await show_sto_detail(query, witel, table_name, sto_selected)
    return ConversationHandler.END

async def handle_gpon_selection(update: Update, context: CallbackContext) -> int:
    """Handler untuk pemilihan GPON"""
    if not await _auth_guard(update):
        return ConversationHandler.END

    query = update.callback_query
    await query.answer()
    gpon_selected = query.data.replace("GPON_", "")
    
    witel = context.user_data.get("witel")
    table_name = context.user_data.get("table_name")

    await show_gpon_detail(query, witel, table_name, gpon_selected)
    return ConversationHandler.END

async def show_sto_detail(query, witel, table_name, sto):
    """Tampilkan detail data untuk STO tertentu"""
    try:
        conn = get_connection_database()
        with conn.cursor() as cursor:
            cursor.execute(f"""
                SELECT 
                    COUNT(*) as total_records,
                    COUNT(DISTINCT nama_gpon) as total_gpon,
                    COUNT(DISTINCT card) as total_card,
                    COUNT(DISTINCT nama_odc) as total_odc
                FROM {table_name}
                WHERE LOWER(witel) = LOWER(%s) AND LOWER(sto) = LOWER(%s)
            """, (witel, sto))
            summary = cursor.fetchone()
            
            # Sample data
            cursor.execute(f"""
                SELECT nama_gpon, card, port, nama_odc, status_feeder
                FROM {table_name}
                WHERE LOWER(witel) = LOWER(%s) AND LOWER(sto) = LOWER(%s)
                ORDER BY nama_gpon, card, port
                LIMIT 10
            """, (witel, sto))
            sample_data = cursor.fetchall()
            
    except Exception as e:
        logging.error(f"Database error: {e}")
        await query.edit_message_text("❌ Gagal mengambil data STO.")
        return
    finally:
        try:
            conn.close()
        except Exception:
            pass

    result_text = f"""🏢 *Detail STO {sto} - {witel}*

📊 *Ringkasan:*
📈 Total Records: {summary['total_records']}
🌐 Total GPON: {summary['total_gpon']}
🔧 Total Card: {summary['total_card']}
🏗 Total ODC: {summary['total_odc']}

📋 *Sample Data (10 pertama):*
"""
    
    for data in sample_data:
        result_text += f"• {data['nama_gpon']} | Card {data['card']}/{data['port']} | {data['nama_odc']} | {data['status_feeder']}\n"
    
    if summary['total_records'] > 10:
        result_text += f"\n_...dan {summary['total_records'] - 10} data lainnya_"

    await query.edit_message_text(result_text, parse_mode="Markdown")

async def show_gpon_detail(query, witel, table_name, gpon):
    """Tampilkan detail data untuk GPON tertentu"""
    try:
        conn = get_connection_database()
        with conn.cursor() as cursor:
            cursor.execute(f"""
                SELECT 
                    sto, ip, card, port, nama_odc, status_feeder,
                    nama_lemari_ftm_eakses, no_panel_eakses, no_port_panel_eakses
                FROM {table_name}
                WHERE LOWER(witel) = LOWER(%s) AND LOWER(nama_gpon) = LOWER(%s)
                ORDER BY sto, card, port
                LIMIT 15
            """, (witel, gpon))
            gpon_data = cursor.fetchall()
            
    except Exception as e:
        logging.error(f"Database error: {e}")
        await query.edit_message_text("❌ Gagal mengambil data GPON.")
        return
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if gpon_data:
        result_text = f"🌐 *Detail GPON {gpon} - {witel}*\n\n"
        for data in gpon_data:
            result_text += f"""📍 *STO:* {data['sto']}
🌐 *IP:* {data['ip']}
🔧 *Card/Port:* {data['card']}/{data['port']}
🏗 *ODC:* {data['nama_odc']}
🟢 *Status:* {data['status_feeder']}
📡 *Lemari:* {data['nama_lemari_ftm_eakses']}
🎛 *Panel:* {data['no_panel_eakses']}/{data['no_port_panel_eakses']}
―――――――――――――――――――――
"""
        
        if len(gpon_data) == 15:
            result_text += "\n_Menampilkan 15 data pertama..._"
    else:
        result_text = f"❌ Tidak ditemukan data untuk GPON {gpon}"

    await query.edit_message_text(result_text, parse_mode="Markdown")

def register_handler(app):
    """Register handler untuk show FTM commands"""
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("showftm", start_showftm)],
        states={
            ASK_WITEL: [CallbackQueryHandler(handle_witel_selection)],
            ASK_OPTION: [CallbackQueryHandler(handle_option_selection)],
            ASK_STO: [CallbackQueryHandler(handle_sto_selection, pattern="^STO_")],
            ASK_GPON: [CallbackQueryHandler(handle_gpon_selection, pattern="^GPON_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )
    app.add_handler(conv_handler)
    
    # Register individual commands
    app.add_handler(CommandHandler("showsto", start_showftm))  # Reuse same handler
    app.add_handler(CommandHandler("showgpon", start_showftm))  # Reuse same handler