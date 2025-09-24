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
from database import get_connection_database
from handler.base_command import cancel
from handler.access_control import is_authorized  # ⬅️ proteksi user terdaftar

ASK_WITEL, ASK_INPUT = range(2)

WITEL_TABLE_MAP = {
    "MALANG": "metro_data_mlg",
    "MADIUN": "metro_data_mdn",
    "KEDIRI": "metro_data_kdr",
}

EXAMPLE_LINK = "https://docs.google.com/spreadsheets/d/15iRZyXPMc79F1lADJtW39sB4QdVsWLBx/edit?usp=sharing&ouid=113431965399677755925&rtpof=true&sd=true"

STO_MASTER = {
    'Metro': {
        'MALANG': ['BTU', 'KPO', 'NTG', 'GKW', 'KEP', 'PGK', 'SBP', 'DPT', 'SBM', 'TUR', 'BNR', 'GDI', 'APG', 'DNO', 'BLB', 'GDG', 'KLJ', 'MLG', 'PKS', 'TMP', 'BRG', 'SWJ', 'LWG', 'SGS'],
        'MADIUN': ['BCR', 'BJN', 'CRB', 'GGR', 'JEN', 'JGO', 'JTR', 'KDU', 'KRJ', 'KRK', 'LOG', 'MGT', 'MNZ', 'MRR', 'MSP', 'NWI', 'PAD', 'PLG', 'PNG', 'PNZ', 'PON', 'RGL', 'SAR', 'SAT', 'SLH', 'SMJ', 'SMO', 'TAW', 'TNZ', 'UTR', 'WKU'],
        'KEDIRI': ['BLR', 'BNU', 'CAT', 'DRN', 'GON', 'GUR', 'KAA', 'KBN', 'KTS', 'KWR', 'LDY', 'MJT', 'NDL', 'NGU', 'NJK', 'PAE', 'PAN', 'PPR', 'PRB', 'PRI', 'SBI', 'SNT', 'TRE', 'TUL', 'WAT', 'WGI', 'WRJ']
    }
}

# ==========================
# AUTH GUARD
# ==========================
async def _auth_guard(update: Update) -> bool:
    user = update.effective_user
    telegram_id = str(user.id) if user else ""
    if is_authorized(telegram_id):
        return True

    # Respons ramah untuk callback & message
    if update.callback_query:
        q = update.callback_query
        await q.answer("Akses ditolak: kamu belum terdaftar.", show_alert=True)
        try:
            await q.message.reply_text(
                "❌ *Akses ditolak*\nKamu belum terdaftar di sistem. Hubungi admin untuk pendaftaran.",
                parse_mode='Markdown'
            )
        except Exception:
            pass
    elif update.message:
        await update.message.reply_text(
            "❌ *Akses ditolak*\nKamu belum terdaftar di sistem. Hubungi admin untuk pendaftaran.",
            parse_mode='Markdown'
        )
    return False

# ==========================
# HANDLERS (logic asli tetap)
# ==========================
async def start_inputmetro(update: Update, context: CallbackContext) -> int:
    if not await _auth_guard(update):
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(k.title(), callback_data=k)] for k in WITEL_TABLE_MAP]
    await update.message.reply_text(
        "📍 Silakan pilih *Witel* terlebih dahulu:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return ASK_WITEL

async def handle_witel_selection(update: Update, context: CallbackContext) -> int:
    if not await _auth_guard(update):
        return ConversationHandler.END

    query = update.callback_query
    await query.answer()
    witel = query.data.upper()
    context.user_data['selected_witel'] = witel
    context.user_data['table_name'] = WITEL_TABLE_MAP.get(witel)

    await query.edit_message_text(
        text=(
            f"✅ Witel dipilih: *{witel}*\n\n"
            f"📎 [Lihat Contoh Format File Excel]({EXAMPLE_LINK})\n"
            f"Silakan kirim file uplink Metro dalam format tersebut."
        ),
        parse_mode='Markdown',
        disable_web_page_preview=True
    )
    return ASK_INPUT

async def main_inputmetro(update: Update, context: CallbackContext) -> int:
    if not await _auth_guard(update):
        return ConversationHandler.END

    file = update.message.document
    table = context.user_data.get('table_name')
    witel = context.user_data.get('selected_witel')

    if not file or not table or not witel:
        await update.message.reply_text("⚠️ Witel belum dipilih. Silakan mulai dari /inputmetro.")
        return ConversationHandler.END

    status_log = ["📂 File diterima."]

    if file.mime_type not in [
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.ms-excel'
    ]:
        await update.message.reply_text("❌ Format file tidak valid. Harap kirim file Excel (.xlsx/.xls) yang sesuai.")
        return ASK_INPUT

    try:
        tg_file = await file.get_file()
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            temp_path = tmp.name
        await tg_file.download_to_drive(temp_path)
        df = pd.read_excel(temp_path)
        os.remove(temp_path)

        df.columns = df.columns.str.lower().str.replace(' ', '_')
        df = df.astype(str).replace([pd.NA, 'nan', 'NaN', '', 'None'], None)
        raw_data = df.to_dict(orient='records')
        status_log.append(f"📄 File berhasil dibaca. Jumlah baris: {len(raw_data)}")
    except Exception as e:
        await update.message.reply_text(f"❌ Gagal membaca file Excel: {e}\n📎 Silakan kirim ulang file yang valid.")
        return ASK_INPUT

    for row in raw_data:
        if row.get("sto"):
            row["sto"] = row["sto"].strip().upper()
        row["witel"] = witel

    required_fields = ["sto", "gpon_hostname", "gpon_intf", "neighbor_hostname"]
    filtered_data = [
        row for row in raw_data
        if all(row.get(f) and str(row.get(f)).strip().lower() not in ['none', 'nan', ''] for f in required_fields)
    ]

    valid_sto_set = set(STO_MASTER['Metro'].get(witel, []))
    invalid_sto = [row["sto"] for row in filtered_data if row.get("sto") and row["sto"] not in valid_sto_set]
    filtered_data = [row for row in filtered_data if row.get("sto") in valid_sto_set]

    if invalid_sto:
        status_log.append(f"⚠️ STO tidak valid ditemukan (contoh): {', '.join(set(invalid_sto[:5]))}")

    status_log.append(f"✅ Data valid ditemukan: {len(filtered_data)} baris.")

    if not filtered_data:
        await update.message.reply_text(
            "\n".join(status_log + [
                "❌ Semua baris memiliki STO yang tidak valid atau kosong.",
                "📎 Silakan kirim ulang file yang sesuai."
            ])
        )
        return ASK_INPUT

    allowed_fields = {
        "witel", "sto", "gpon_hostname", "gpon_ip", "gpon_merk", "gpon_tipe",
        "gpon_merk_tipe", "gpon_intf", "gpon_lacp",
        "neighbor_hostname", "neighbor_intf", "neighbor_lacp",
        "bw", "sfp", "vlan_sip", "vlan_internet", "keterangan", "otn", "port"
    }

    uplink_data = [{k: row.get(k) for k in allowed_fields} for row in filtered_data]
    sto_set = {row["sto"] for row in uplink_data if row.get("sto")}

    status_log.append(f"📌 STO diproses: {', '.join(sorted(sto_set))}")
    status_log.append("💾 Menyimpan data ke database...")

    conn = get_connection_database()
    try:
        with conn.cursor() as cursor:
            delete_sql = f"DELETE FROM {table} WHERE sto IN ({','.join(['%s'] * len(sto_set))})"
            cursor.execute(delete_sql, list(sto_set))

            insert_sql = f"""
                INSERT INTO {table} (
                    witel, sto, gpon_hostname, gpon_ip, gpon_merk, gpon_tipe,
                    gpon_merk_tipe, gpon_intf, gpon_lacp,
                    neighbor_hostname, neighbor_intf, neighbor_lacp,
                    bw, sfp, vlan_sip, vlan_internet, keterangan, otn, port
                ) VALUES (
                    %(witel)s, %(sto)s, %(gpon_hostname)s, %(gpon_ip)s, %(gpon_merk)s, %(gpon_tipe)s,
                    %(gpon_merk_tipe)s, %(gpon_intf)s, %(gpon_lacp)s,
                    %(neighbor_hostname)s, %(neighbor_intf)s, %(neighbor_lacp)s,
                    %(bw)s, %(sfp)s, %(vlan_sip)s, %(vlan_internet)s, %(keterangan)s, %(otn)s, %(port)s
                )
            """
            cursor.executemany(insert_sql, uplink_data)
            conn.commit()
    except Exception as e:
        await update.message.reply_text(f"❌ Gagal menyimpan ke database: {e}")
        return ASK_INPUT
    finally:
        try:
            conn.close()
        except Exception:
            pass

    status_log.append("✅ *Hasil Input Data Metro:*")
    status_log.append(f"- Witel: *{witel.upper()}*")
    status_log.append(f"- Total STO dioverwrite: {len(sto_set)}")
    status_log.append(f"- Total Baris Disimpan: {len(uplink_data)}")
    status_log.append("\n📎 Silakan kirim file berikutnya untuk STO lain.\n❌ Atau ketik /cancel untuk mengakhiri proses.")

    await update.message.reply_text("\n".join(status_log), parse_mode="Markdown")
    return ASK_INPUT

async def restart(update: Update, context: CallbackContext) -> int:
    if not await _auth_guard(update):
        return ConversationHandler.END
    return await start_inputmetro(update, context)

def register_handler(rh):
    rh.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler('inputmetro', start_inputmetro)],
            states={
                ASK_WITEL: [CallbackQueryHandler(handle_witel_selection)],
                ASK_INPUT: [MessageHandler(filters.Document.ALL, main_inputmetro)],
            },
            fallbacks=[
                CommandHandler('cancel', cancel),
                CommandHandler('start', restart),
                CommandHandler('inputmetro', restart)
            ],
            allow_reentry=True
        )
    )
