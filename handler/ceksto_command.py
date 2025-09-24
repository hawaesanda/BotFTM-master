from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    CallbackContext, ConversationHandler,
    CommandHandler, CallbackQueryHandler
)
from telegram.constants import ParseMode
from database import get_connection_database
from handler.access_control import is_authorized  # ⬅️ proteksi akses
import logging

CHOOSE_DATA_TYPE, CHOOSE_WITEL = range(2)

TABLE_MAP = {
    'FTM': {
        'Malang': 'ftm_data_mlg',
        'Madiun': 'ftm_data_mdn',
        'Kediri': 'ftm_data_kdr',
    },
    'Metro': {
        'Malang': 'metro_data_mlg',
        'Madiun': 'metro_data_mdn',
        'Kediri': 'metro_data_kdr',
    }
}

STO_MASTER = {
    'FTM': {
        'Malang': ['BTU', 'KPO', 'NTG', 'GKW', 'KEP', 'PGK', 'SBP', 'DPT', 'SBM', 'TUR', 'BNR', 'GDI', 'APG', 'DNO', 'BLB', 'GDG', 'KLJ', 'MLG', 'PKS', 'TMP', 'BRG', 'SWJ', 'LWG', 'SGS'],
        'Madiun': ['BCR', 'BJN', 'CRB', 'GGR', 'JEN', 'JGO', 'JTR', 'KDU', 'KRJ', 'KRK', 'LOG', 'MGT', 'MNZ', 'MRR', 'MSP', 'NWI', 'PAD', 'PLG', 'PNG', 'PNZ', 'PON', 'RGL', 'SAR', 'SAT', 'SLH', 'SMJ', 'SMO', 'TAW', 'TNZ', 'UTR', 'WKU'],
        'Kediri': ['BLR', 'BNU', 'CAT', 'DRN', 'GON', 'GUR', 'KAA', 'KBN', 'KTS', 'KWR', 'LDY', 'MJT', 'NDL', 'NGU', 'NJK', 'PAE', 'PAN', 'PPR', 'PRB', 'PRI', 'SBI', 'SNT', 'TRE', 'TUL', 'WAT', 'WGI', 'WRJ']
    },
    'Metro': {
        'Malang': ['BTU', 'KPO', 'NTG', 'GKW', 'KEP', 'PGK', 'SBP', 'DPT', 'SBM', 'TUR', 'BNR', 'GDI', 'APG', 'DNO', 'BLB', 'GDG', 'KLJ', 'MLG', 'PKS', 'TMP', 'BRG', 'SWJ', 'LWG', 'SGS'],
        'Madiun': ['BCR', 'BJN', 'CRB', 'GGR', 'JEN', 'JGO', 'JTR', 'KDU', 'KRJ', 'KRK', 'LOG', 'MGT', 'MNZ', 'MRR', 'MSP', 'NWI', 'PAD', 'PLG', 'PNG', 'PNZ', 'PON', 'RGL', 'SAR', 'SAT', 'SLH', 'SMJ', 'SMO', 'TAW', 'TNZ', 'UTR', 'WKU'],
        'Kediri': ['BLR', 'BNU', 'CAT', 'DRN', 'GON', 'GUR', 'KAA', 'KBN', 'KTS', 'KWR', 'LDY', 'MJT', 'NDL', 'NGU', 'NJK', 'PAE', 'PAN', 'PPR', 'PRB', 'PRI', 'SBI', 'SNT', 'TRE', 'TUL', 'WAT', 'WGI', 'WRJ']
    }
}

async def _auth_guard(update: Update) -> bool:
    user = update.effective_user
    telegram_id = str(user.id) if user else ""
    if is_authorized(telegram_id):
        return True

    # respons ramah untuk kedua jenis input
    if update.callback_query:
        q = update.callback_query
        await q.answer("Akses ditolak: Anda belum terdaftar sebagai user.", show_alert=True)
        try:
            await q.message.reply_text(
                "❌ *Akses ditolak*\nAnda belum terdaftar di sistem. Silahkan lakukan pendaftaran dengan register.",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            pass
    elif update.message:
        await update.message.reply_text(
            "❌ *Akses ditolak*\nAnda belum terdaftar di sistem. Silahkan lakukan pendaftaran dengan register.",
            parse_mode=ParseMode.MARKDOWN
        )
    return False

async def start_ceksto(update: Update, context: CallbackContext) -> int:
    if not await _auth_guard(update):
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("🔌 FTM", callback_data="FTM")],
        [InlineKeyboardButton("🌐 Metro", callback_data="Metro")]
    ]
    await update.message.reply_text(
        "📊 Pilih jenis data STO yang ingin dicek:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSE_DATA_TYPE

async def choose_data_type(update: Update, context: CallbackContext) -> int:
    if not await _auth_guard(update):
        return ConversationHandler.END

    query = update.callback_query
    await query.answer()
    data_type = query.data
    context.user_data["data_type"] = data_type

    keyboard = [[InlineKeyboardButton(witel, callback_data=witel)] for witel in TABLE_MAP[data_type].keys()]
    await query.edit_message_text(
        f"✅ Jenis data *{data_type}* dipilih.\n\nSekarang pilih *WITEL*:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSE_WITEL

async def choose_witel(update: Update, context: CallbackContext) -> int:
    if not await _auth_guard(update):
        return ConversationHandler.END

    query = update.callback_query
    await query.answer()

    witel = query.data
    data_type = context.user_data["data_type"]
    context.user_data["witel"] = witel

    table_name = TABLE_MAP[data_type][witel]
    sto_master = STO_MASTER[data_type][witel]

    try:
        conn = get_connection_database()
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT DISTINCT sto FROM {table_name}")
            db_sto = {row['sto'].upper() for row in cursor.fetchall()}
    except Exception as e:
        logging.error(f"DB Error: {e}")
        await query.edit_message_text("❌ Gagal mengakses database.")
        return ConversationHandler.END
    finally:
        try:
            conn.close()
        except Exception:
            pass

    result_text = f"📋 *Status STO - {data_type} - {witel}*\n\n"
    for idx, sto in enumerate(sto_master, start=1):
        status = '✔️' if sto in db_sto else '❌'
        result_text += f"{idx}. {sto} {status}\n"

    await query.edit_message_text(result_text, parse_mode="Markdown")
    return ConversationHandler.END

def register_handler(app):
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("ceksto", start_ceksto)],
        states={
            CHOOSE_DATA_TYPE: [CallbackQueryHandler(choose_data_type)],
            CHOOSE_WITEL: [CallbackQueryHandler(choose_witel)]
        },
        fallbacks=[],
        allow_reentry=True,
    )
    app.add_handler(conv_handler)
