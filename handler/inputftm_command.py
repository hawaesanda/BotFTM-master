import os
import tempfile
import pandas as pd
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
from handler.base_command import cancel
from handler.access_control import is_authorized  # ⬅️ proteksi akses
# from handler.access_control import is_admin     # ⬅️ pakai ini jika mau khusus admin

ASK_WITEL, ASK_INPUT = range(2)

EXAMPLE_LINK = "https://docs.google.com/spreadsheets/d/1bI1CQ44VFmTKug_S6m2m2vmORTV2JUwg/edit?usp=drive_link&ouid=113431965399677755925&rtpof=true&sd=true"

STO_MASTER = {
    'FTM': {
        'mlg': ['BTU', 'KPO', 'NTG', 'GKW', 'KEP', 'PGK', 'SBP', 'DPT', 'SBM', 'TUR', 'BNR', 'GDI', 'APG', 'DNO', 'BLB', 'GDG', 'KLJ', 'MLG', 'PKS', 'TMP', 'BRG', 'SWJ', 'LWG', 'SGS'],
        'mdn': ['BCR', 'BJN', 'CRB', 'GGR', 'JEN', 'JGO', 'JTR', 'KDU', 'KRJ', 'KRK', 'LOG', 'MGT', 'MNZ', 'MRR', 'MSP', 'NWI', 'PAD', 'PLG', 'PNG', 'PNZ', 'PON', 'RGL', 'SAR', 'SAT', 'SLH', 'SMJ', 'SMO', 'TAW', 'TNZ', 'UTR', 'WKU'],
        'kdr': ['BLR', 'BNU', 'CAT', 'DRN', 'GON', 'GUR', 'KAA', 'KBN', 'KTS', 'KWR', 'LDY', 'MJT', 'NDL', 'NGU', 'NJK', 'PAE', 'PAN', 'PPR', 'PRB', 'PRI', 'SBI', 'SNT', 'TRE', 'TUL', 'WAT', 'WGI', 'WRJ']
    }
}

WITEL_TABLES = {
    "mlg": "ftm_data_mlg",
    "kdr": "ftm_data_kdr",
    "mdn": "ftm_data_mdn"
}

async def _auth_guard(update: Update) -> bool:
    user = update.effective_user
    telegram_id = str(user.id) if user else ""
    allowed = is_authorized(telegram_id)  # or: is_admin(telegram_id)
    if allowed:
        return True

    # Respon ramah untuk callback & message
    if update.callback_query:
        q = update.callback_query
        await q.answer("Akses ditolak: Anda belum terdaftar sebagai user.", show_alert=True)
        try:
            await q.message.reply_text(
                "❌ *Akses ditolak*\nAnda belum terdaftar di sistem. Silahkan lakukan pendaftaran dengan register.",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception:
            pass
    elif update.message:
        await update.message.reply_text(
            "❌ *Akses ditolak*\nAnda belum terdaftar di sistem. Silahkan lakukan pendaftaran dengan register.",
            parse_mode=ParseMode.MARKDOWN,
        )
    return False

async def start_inputftm(update: Update, context: CallbackContext) -> int:
    if not await _auth_guard(update):
        return ConversationHandler.END

    keyboard = [[
        InlineKeyboardButton("Malang", callback_data="mlg"),
        InlineKeyboardButton("Kediri", callback_data="kdr"),
        InlineKeyboardButton("Madiun", callback_data="mdn"),
    ]]
    await update.message.reply_text(
        "📍 Pilih *WITEL* tujuan input data:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return ASK_WITEL

async def choose_witel(update: Update, context: CallbackContext) -> int:
    if not await _auth_guard(update):
        return ConversationHandler.END

    query = update.callback_query
    await query.answer()

    witel_code = query.data
    context.user_data["witel_code"] = witel_code

    await query.edit_message_text(
        text=(
            f"📂 Witel dipilih: *{witel_code.upper()}*\n\n"
            f"📎 [Lihat Contoh Format File Excel]({EXAMPLE_LINK})\n"
            f"Setelah itu silakan *unggah file Excel* kamu."
        ),
        parse_mode='Markdown',
        disable_web_page_preview=True
    )
    return ASK_INPUT

async def main_inputftm(update: Update, context: CallbackContext) -> int:
    if not await _auth_guard(update):
        return ConversationHandler.END

    file = update.message.document
    table_code = context.user_data.get("witel_code")

    if not table_code or table_code not in WITEL_TABLES:
        await update.message.reply_text("⚠️ Witel tidak valid. Silakan mulai kembali dengan /inputftm.")
        return ConversationHandler.END

    table_name = WITEL_TABLES[table_code]
    status_log = ["📂 File diterima."]

    if not file or file.mime_type not in [
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.ms-excel'
    ]:
        await update.message.reply_text("❌ Format file salah! Harap kirim file Excel (.xlsx/.xls) yang valid.")
        return ASK_INPUT

    processed_file = await file.get_file()
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        temp_path = tmp.name
    await processed_file.download_to_drive(temp_path)

    try:
        df = pd.read_excel(temp_path)
        df.columns = df.columns.str.lower().str.replace(" ", "_")
        df = df.astype(str).replace([pd.NA, 'nan', 'NaN', ''], None)
        records = df.to_dict(orient="records")
        status_log.append(f"📄 File berhasil dibaca. Jumlah baris: {len(records)}")
    except Exception as e:
        os.remove(temp_path)
        await update.message.reply_text(f"❌ Gagal membaca file Excel: {e}\n📎 Silakan kirim ulang file yang valid.")
        return ASK_INPUT
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    fields = {
        "witel", "sto", "nama_gpon", "ip", "card", "port",
        "nama_lemari_ftm_eakses", "no_panel_eakses", "no_port_panel_eakses",
        "nama_lemari_ftm_oakses", "no_panel_oakses", "no_port_panel_oakses",
        "no_core_feeder", "nama_segmen_feeder_utama", "status_feeder",
        "kapasitas_kabel_feeder_utama", "nama_odc"
    }

    data_transformed = []
    for row in records:
        item = {key: row.get(key) for key in fields}
        if item.get("sto"):
            item["sto"] = item["sto"].strip().upper()
        if item.get("witel"):
            item["witel"] = item["witel"].strip()
        if item.get("sto") and item.get("nama_gpon") and item.get("card") and item.get("port"):
            data_transformed.append(item)

    valid_sto_list = STO_MASTER['FTM'].get(table_code, [])
    valid_sto_set = set(valid_sto_list)
    data_valid_sto = [row for row in data_transformed if row.get("sto") in valid_sto_set]
    invalid_sto = [row["sto"] for row in data_transformed if row.get("sto") and row["sto"] not in valid_sto_set]

    if invalid_sto:
        status_log.append(f"⚠️ Ditemukan STO tidak valid (contoh): {', '.join(sorted(set(invalid_sto[:5])))}")

    status_log.append(f"✅ Data valid ditemukan: {len(data_valid_sto)} baris.")

    if not data_valid_sto:
        await update.message.reply_text(
            "\n".join(status_log + [
                "❌ Semua baris memiliki STO yang tidak valid.",
                "📎 Silakan periksa kembali dan kirim ulang file yang benar."
            ])
        )
        return ASK_INPUT

    sto_set = {row["sto"] for row in data_valid_sto if row.get("sto")}
    status_log.append(f"📌 STO diproses: {', '.join(sorted(sto_set))}")
    status_log.append("💾 Menyimpan data ke database...")

    conn = get_connection_database()
    try:
        with conn.cursor() as cursor:
            delete_sql = f"DELETE FROM {table_name} WHERE sto IN ({','.join(['%s'] * len(sto_set))})"
            cursor.execute(delete_sql, list(sto_set))

            insert_sql = f"""
                INSERT INTO {table_name} (
                    witel, sto, nama_gpon, ip, card, port,
                    nama_lemari_ftm_eakses, no_panel_eakses, no_port_panel_eakses,
                    nama_lemari_ftm_oakses, no_panel_oakses, no_port_panel_oakses,
                    no_core_feeder, nama_segmen_feeder_utama, status_feeder,
                    kapasitas_kabel_feeder_utama, nama_odc
                ) VALUES (
                    %(witel)s, %(sto)s, %(nama_gpon)s, %(ip)s, %(card)s, %(port)s,
                    %(nama_lemari_ftm_eakses)s, %(no_panel_eakses)s, %(no_port_panel_eakses)s,
                    %(nama_lemari_ftm_oakses)s, %(no_panel_oakses)s, %(no_port_panel_oakses)s,
                    %(no_core_feeder)s, %(nama_segmen_feeder_utama)s, %(status_feeder)s,
                    %(kapasitas_kabel_feeder_utama)s, %(nama_odc)s
                )
            """
            cursor.executemany(insert_sql, data_valid_sto)
            conn.commit()
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        await update.message.reply_text(f"❌ Gagal menyimpan ke database: {e}")
        return ASK_INPUT
    try:
        conn.close()
    except Exception:
        pass

    status_log.append("✅ *Hasil Input Data:*")
    status_log.append(f"- Witel: *{table_code.upper()}*")
    status_log.append(f"- Total STO yang dioverwrite: {len(sto_set)}")
    status_log.append(f"- Total Baris Disimpan: {len(data_valid_sto)}")
    status_log.append("\n📎 Silakan kirim file Excel berikutnya untuk STO lain.\n❌ Atau ketik /cancel untuk mengakhiri proses.")

    await update.message.reply_text(
        "\n".join(status_log),
        parse_mode="Markdown"
    )
    return ASK_INPUT

async def restart(update: Update, context: CallbackContext) -> int:
    if not await _auth_guard(update):
        return ConversationHandler.END
    return await start_inputftm(update, context)

def register_handler(rh):
    rh.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler('inputftm', start_inputftm)],
            states={
                ASK_WITEL: [CallbackQueryHandler(choose_witel)],
                ASK_INPUT: [MessageHandler(filters.Document.ALL, main_inputftm)]
            },
            fallbacks=[
                CommandHandler('cancel', cancel),
                CommandHandler('start', restart),
                CommandHandler('inputftm', restart)
            ],
            allow_reentry=True
        )
    )
