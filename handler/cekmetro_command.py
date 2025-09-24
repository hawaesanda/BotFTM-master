from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CallbackContext, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters
)
from telegram.constants import ParseMode
from database import get_connection_database
from handler.base_command import cancel
from handler.access_control import is_authorized  # ⬅️ pakai authorisasi JSON
from html import escape
from collections import defaultdict, Counter

ASK_WITEL, ASK_STO, ASK_GPON, SHOW_RESULT = range(4)

WITEL_TABLE_MAP = {
    "MALANG": "metro_data_mlg",
    "MADIUN": "metro_data_mdn",
    "KEDIRI": "metro_data_kdr",
}

def chunk_list(lst, n):
    return [lst[i:i + n] for i in range(0, len(lst), n)]

def format_counter(counter_dict):
    return ', '.join([f"{v} × {k}" for k, v in counter_dict.items()])

async def _auth_guard(update: Update) -> bool:
    user = update.effective_user
    telegram_id = str(user.id) if user else ""
    if is_authorized(telegram_id):
        return True

    if update.callback_query:
        q = update.callback_query
        await q.answer("Akses ditolak: Anda belum terdaftar sebagai user.", show_alert=True)
        try:
            await q.message.reply_text(
                "❌ <b>Akses ditolak</b>\nAnda belum terdaftar di sistem. Silahkan lakukan pendaftaran dengan register.",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass
    elif update.message:
        await update.message.reply_text(
            "❌ <b>Akses ditolak</b>\nAnda belum terdaftar di sistem. Silahkan lakukan pendaftaran dengan register.",
            parse_mode=ParseMode.HTML
        )
    return False

async def start_cekmetro(update: Update, context: CallbackContext) -> int:
    if not await _auth_guard(update):
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("Malang", callback_data="MALANG")],
        [InlineKeyboardButton("Madiun", callback_data="MADIUN")],
        [InlineKeyboardButton("Kediri", callback_data="KEDIRI")]
    ]
    await update.message.reply_text(
        "📍 Silakan pilih <b>Witel</b> terlebih dahulu:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )
    return ASK_WITEL

async def handle_witel_selection(update: Update, context: CallbackContext) -> int:
    if not await _auth_guard(update):
        return ConversationHandler.END

    query = update.callback_query
    await query.answer()
    witel = query.data
    context.user_data["selected_witel"] = witel
    context.user_data["table_name"] = WITEL_TABLE_MAP[witel]

    try:
        conn = get_connection_database()
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT DISTINCT sto FROM {WITEL_TABLE_MAP[witel]} WHERE LOWER(witel) = LOWER(%s) ORDER BY sto",
                (witel,)
            )
            sto_rows = cursor.fetchall()
            sto_list = [row["sto"] for row in sto_rows if row["sto"]]
    except Exception as e:
        await query.edit_message_text(f"❌ Gagal mengambil daftar STO: {escape(str(e))}")
        return ConversationHandler.END
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if not sto_list:
        await query.edit_message_text("⚠️ Tidak ditemukan data STO.")
        return ConversationHandler.END

    buttons = chunk_list([InlineKeyboardButton(sto, callback_data=f"sto_{sto}") for sto in sto_list], 3)
    await query.edit_message_text(
        f"✅ Witel <b>{escape(witel)}</b> dipilih.\n\nSilakan pilih <b>STO</b> yang tersedia:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return ASK_STO

async def handle_sto_selection(update: Update, context: CallbackContext) -> int:
    if not await _auth_guard(update):
        return ConversationHandler.END

    query = update.callback_query
    await query.answer()
    sto = query.data.replace("sto_", "")
    context.user_data["selected_sto"] = sto
    table = context.user_data["table_name"]

    try:
        conn = get_connection_database()
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT DISTINCT gpon_hostname FROM {table}
                WHERE LOWER(sto) = LOWER(%s)
                ORDER BY gpon_hostname
                """,
                (sto,)
            )
            results = cursor.fetchall()
            gpons = [r["gpon_hostname"] for r in results if r["gpon_hostname"]]
    except Exception as e:
        await query.edit_message_text(f"❌ Gagal ambil gpon_hostname: {escape(str(e))}")
        return ConversationHandler.END
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if not gpons:
        await query.edit_message_text("❌ Tidak ada GPON Hostname ditemukan.")
        return ConversationHandler.END

    context.user_data["gpon_hostnames"] = gpons
    buttons = chunk_list([InlineKeyboardButton(h, callback_data=f"gpon_{h}") for h in gpons], 3)

    await query.edit_message_text(
        f"✅ STO <b>{escape(sto)}</b> dipilih.\n\nSilakan pilih <b>GPON Hostname</b>:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return ASK_GPON

def _build_metro_message(
    row_sample: dict,
    gpon_intfs: list,
    neighbor_intfs: list,
    sfp_counter: Counter,
    bw_counter: Counter,
    header: str = "📅 <b>Data Metro</b>",
    hide_otn_port: bool = False,
    override_gpon_lacp: str | None = None,
    extra_lines: str = ""
) -> str:
    """
    Susun blok pesan dengan format seragam.
    - gpon_intfs: list of interfaces (akan ditampilkan menumpuk).
    - hide_otn_port: True untuk menyembunyikan baris OTN & Port (dipakai di otn_kosong).
    - override_gpon_lacp: pakai nilai ini bila perlu (mis. dari key grouping).
    - extra_lines: baris tambahan opsional (mis. Neighbor LACP).
    """
    hostname = row_sample.get("gpon_hostname") or "-"
    gpon_ip = row_sample.get("gpon_ip") or "-"
    merk_tipe = row_sample.get("gpon_merk_tipe") or "-"
    gpon_lacp = override_gpon_lacp if override_gpon_lacp is not None else (row_sample.get("gpon_lacp") or "-")

    # Tampilkan GPON Intf menumpuk
    gpon_intfs = sorted(set(filter(None, gpon_intfs)))
    if gpon_intfs:
        gpon_intfs_str = "\n".join([f"• {escape(x)}" for x in gpon_intfs])
    else:
        gpon_intfs_str = "-"

    neighbor_str = "\n".join([f"• {escape(x)}" for x in sorted(set(filter(None, neighbor_intfs)))]) or "-"

    sfp_str = format_counter(sfp_counter) or "-"
    bw_str = format_counter(bw_counter) or "-"

    lines = [
        f"{header}",
        f"🖥 <b>GPON Hostname:</b> {escape(hostname)}",
        f"🌐 <b>GPON IP:</b> {escape(gpon_ip)}",
        f"🛠 <b>Merk/Tipe:</b> {escape(merk_tipe)}",
        f"🔗 <b>GPON LACP:</b> {escape(gpon_lacp)}",
    ]
    if extra_lines:
        lines.append(extra_lines)

    # GPON Intf blok multi-baris
    lines.append("🔌 <b>GPON Intf:</b>")
    lines.append(gpon_intfs_str)

    # OTN/Port hanya jika tidak disembunyikan dan memang ada
    if not hide_otn_port:
        otn = row_sample.get("otn")
        port = row_sample.get("port")
        if otn or port:
            if otn:
                lines.append(f"🧹 <b>OTN:</b> {escape(otn)}")
            if port:
                lines.append(f"🔌 <b>Port:</b> {escape(port)}")

    # Bagian agregat
    lines.extend([
        "↔️ <b>Neighbor Intf:</b>",
        neighbor_str,
        f"💡 <b>SFP:</b> {escape(sfp_str)}",
        f"📆 <b>BW:</b> {escape(bw_str)}",
    ])

    return "\n".join(lines).strip()

async def handle_gpon_selection(update: Update, context: CallbackContext) -> int:
    if not await _auth_guard(update):
        return ConversationHandler.END

    query = update.callback_query
    await query.answer()
    gpon = query.data.replace("gpon_", "")
    context.user_data["selected_gpon"] = gpon
    sto = context.user_data["selected_sto"]
    table = context.user_data["table_name"]

    try:
        conn = get_connection_database()
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT * FROM {table}
                WHERE LOWER(sto) = LOWER(%s)
                AND LOWER(gpon_hostname) = LOWER(%s)
                """,
                (sto, gpon)
            )
            results = cursor.fetchall()
    except Exception as e:
        await query.edit_message_text(f"❌ Gagal ambil data: {escape(str(e))}")
        return ConversationHandler.END
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if not results:
        await query.edit_message_text("⚠️ Data tidak ditemukan.")
        return ConversationHandler.END

    otn_kosong = []
    otn_ada = []
    for row in results:
        if row.get("otn"):
            otn_ada.append(row)
        else:
            otn_kosong.append(row)

    # === OTN KOSONG: tampilkan tanpa OTN/Port, GPON Intf ditumpuk ===
    if otn_kosong:
        grouped = defaultdict(list)
        # Group by (gpon_lacp, neighbor_lacp)
        for row in otn_kosong:
            key = (row.get("gpon_lacp") or "-", row.get("neighbor_lacp") or "-")
            grouped[key].append(row)

        for (g_lacp, n_lacp), group_rows in grouped.items():
            sample = group_rows[0]
            gpon_intfs = [r.get("gpon_intf") for r in group_rows if r.get("gpon_intf")]
            neighbor_intfs = [r.get("neighbor_intf") for r in group_rows if r.get("neighbor_intf")]
            sfp_counter = Counter([r.get("sfp") for r in group_rows if r.get("sfp")])
            bw_counter = Counter([r.get("bw") for r in group_rows if r.get("bw")])

            extra = f"🧭 <b>Neighbor LACP:</b> {escape(n_lacp)}"
            msg = _build_metro_message(
                row_sample=sample,
                gpon_intfs=gpon_intfs,
                neighbor_intfs=neighbor_intfs,
                sfp_counter=sfp_counter,
                bw_counter=bw_counter,
                header="📅 <b>Data Metro (Tidak melalui OTN)</b>",
                hide_otn_port=True,                 # ⬅️ sembunyikan OTN/Port
                override_gpon_lacp=g_lacp,
                extra_lines=extra
            )
            await query.message.reply_text(msg, parse_mode=ParseMode.HTML)

    # === OTN ADA: pakai template yang sama, Intf ditumpuk, OTN/Port ditampilkan bila ada ===
    if otn_ada:
        grouped = defaultdict(list)
        # Group by gpon_hostname
        for row in otn_ada:
            key = row.get("gpon_hostname") or "-"
            grouped[key].append(row)

        for hostname, group_rows in grouped.items():
            sample = group_rows[0]
            gpon_intfs = [r.get("gpon_intf") for r in group_rows if r.get("gpon_intf")]
            neighbor_intfs = [r.get("neighbor_intf") for r in group_rows if r.get("neighbor_intf")]
            sfp_counter = Counter([r.get("sfp") for r in group_rows if r.get("sfp")])
            bw_counter = Counter([r.get("bw") for r in group_rows if r.get("bw")])

            msg = _build_metro_message(
                row_sample=sample,
                gpon_intfs=gpon_intfs,
                neighbor_intfs=neighbor_intfs,
                sfp_counter=sfp_counter,
                bw_counter=bw_counter,
                header="📅 <b>Data Metro</b>",
                hide_otn_port=False,   # hanya muncul kalau field-nya ada
            )
            await query.message.reply_text(msg, parse_mode=ParseMode.HTML)

    return ConversationHandler.END

def register_handler(app):
    app.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler("cekmetro", start_cekmetro)],
            states={
                ASK_WITEL: [CallbackQueryHandler(handle_witel_selection)],
                ASK_STO: [CallbackQueryHandler(handle_sto_selection, pattern="^sto_")],
                ASK_GPON: [CallbackQueryHandler(handle_gpon_selection, pattern="^gpon_")],
            },
            fallbacks=[CommandHandler("cancel", cancel)],
            allow_reentry=True,
        )
    )
