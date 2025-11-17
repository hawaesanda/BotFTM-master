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
# States for /infoSTO command
INFO_CHOOSE_WITEL, INFO_CHOOSE_STO = range(2, 4)

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
    sto_master = sorted(STO_MASTER[data_type][witel])

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

    # ----------------------------
    # /infoSTO - show detailed info per STO (Metro)
    # ----------------------------
    async def start_info_sto(update: Update, context: CallbackContext) -> int:
        if not await _auth_guard(update):
            return ConversationHandler.END
        # only Metro as requested
        keyboard = [
            [InlineKeyboardButton("Malang", callback_data="Malang")],
            [InlineKeyboardButton("Madiun", callback_data="Madiun")],
            [InlineKeyboardButton("Kediri", callback_data="Kediri")],
        ]
        await update.message.reply_text(
            "📍 Pilih Witel (Metro) untuk melihat info STO:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return INFO_CHOOSE_WITEL

    async def handle_info_witel(update: Update, context: CallbackContext) -> int:
        if not await _auth_guard(update):
            return ConversationHandler.END
        query = update.callback_query
        await query.answer()
        witel = query.data
        context.user_data["info_witel"] = witel

        # use STO_MASTER for Metro and show in sorted (alphabetical) order
        sto_list = sorted(STO_MASTER.get('Metro', {}).get(witel, []))
        if not sto_list:
            await query.edit_message_text("⚠️ Tidak ada daftar STO untuk witel ini.")
            return ConversationHandler.END

        buttons = []
        for i in range(0, len(sto_list), 3):
            row = [InlineKeyboardButton(sto, callback_data=f"INFOSTO_{sto}") for sto in sto_list[i:i+3]]
            buttons.append(row)

        await query.edit_message_text(
            f"✅ Witel *{witel}* dipilih. Pilih STO untuk melihat info detail:",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return INFO_CHOOSE_STO

    async def handle_info_sto_selection(update: Update, context: CallbackContext) -> int:
        if not await _auth_guard(update):
            return ConversationHandler.END
        query = update.callback_query
        await query.answer()
        sto = query.data.replace("INFOSTO_", "")
        witel = context.user_data.get("info_witel")

        table = TABLE_MAP.get('Metro', {}).get(witel)
        if not table:
            await query.edit_message_text("❌ Tabel untuk witel tidak ditemukan.")
            return ConversationHandler.END

        # Query database for summary metrics
        try:
            conn = get_connection_database()
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT COUNT(*) as total_records, COUNT(DISTINCT gpon_hostname) as total_gpon,"
                    f" SUM(CASE WHEN otn IS NOT NULL AND otn != '' THEN 1 ELSE 0 END) as total_otn"
                    f" FROM {table} WHERE LOWER(sto)=LOWER(%s)",
                    (sto,)
                )
                summary = cursor.fetchone()

                # distribution by merk/tipe: count UNIQUE gpon_hostnames per merk
                cursor.execute(
                    f"SELECT COALESCE(gpon_merk_tipe, gpon_merk, 'Unknown') as merk, COUNT(DISTINCT gpon_hostname) as cnt"
                    f" FROM {table} WHERE LOWER(sto)=LOWER(%s) GROUP BY merk ORDER BY cnt DESC LIMIT 10",
                    (sto,)
                )
                merk_rows = cursor.fetchall()

                # list of GPON hostnames that go through OTN (if any)
                cursor.execute(
                    f"SELECT DISTINCT gpon_hostname FROM {table} WHERE LOWER(sto)=LOWER(%s) AND otn IS NOT NULL AND otn != '' ORDER BY gpon_hostname",
                    (sto,)
                )
                otn_gpons = [r['gpon_hostname'] for r in cursor.fetchall() if r.get('gpon_hostname')]

        except Exception as e:
            logging.error(f"DB Error infoSTO: {e}")
            await query.edit_message_text("❌ Gagal mengambil informasi dari database.")
            return ConversationHandler.END
        finally:
            try:
                conn.close()
            except Exception:
                pass

        # Build message
        total_gpon = summary.get('total_gpon') if summary else 0
        total_otn = summary.get('total_otn') if summary else 0

        msg_lines = [
            f"📋 *Info STO - {sto} ({witel})*",
            "",
            f"🌐 *Total GPON:* {total_gpon}",
            "",
        ]

        # OTN status (simple)
        if total_otn and int(total_otn) > 0:
            msg_lines.append("🔌 *OTN:* Melalui OTN")
        else:
            msg_lines.append("🔌 *OTN:* Tidak melalui OTN")

        # Separator then merk distribution
        msg_lines.append("")
        msg_lines.append("📊 *Merk GPON:*")

        if merk_rows:
            for r in merk_rows:
                msg_lines.append(f"- {r['merk']} x {r['cnt']}")
        else:
            msg_lines.append("- Tidak ada data merk/tipe")

        await query.edit_message_text("\n".join(msg_lines), parse_mode='Markdown')
        return ConversationHandler.END

    # register ConversationHandler for infoSTO
    info_conv = ConversationHandler(
        entry_points=[CommandHandler('infosto', start_info_sto), CommandHandler('infoSTO', start_info_sto)],
        states={
            INFO_CHOOSE_WITEL: [CallbackQueryHandler(handle_info_witel)],
            INFO_CHOOSE_STO: [CallbackQueryHandler(handle_info_sto_selection, pattern=r"^INFOSTO_")]
        },
        fallbacks=[],
        allow_reentry=True,
    )
    app.add_handler(info_conv)
