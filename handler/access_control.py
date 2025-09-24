import json
import os

ALLOWED_USERS_FILE = "allowed_users.json"


def load_allowed_users() -> list[dict]:
    """Membaca semua user dari JSON."""
    if not os.path.exists(ALLOWED_USERS_FILE):
        return []
    with open(ALLOWED_USERS_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []

def save_allowed_users(users: list[dict]) -> None:
    """Simpan semua user ke JSON."""
    with open(ALLOWED_USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)


def is_authorized(telegram_id: str) -> bool:
    """Cek apakah Telegram ID terdaftar sebagai user."""
    users = load_allowed_users()
    return any(u["telegram_id"] == telegram_id for u in users)


def is_admin(telegram_id: str) -> bool:
    """Cek apakah Telegram ID adalah admin."""
    users = load_allowed_users()
    return any(u["telegram_id"] == telegram_id and u["role"] == "admin" for u in users)


def add_allowed_user(name: str, nik: str, telegram_id: str, role: str = "user") -> bool:
    """Tambahkan user baru ke daftar JSON."""
    users = load_allowed_users()
    if any(u["telegram_id"] == telegram_id for u in users):
        return False
    users.append({"name": name, "nik": nik, "telegram_id": telegram_id, "role": role})
    save_allowed_users(users)
    return True


def remove_allowed_user(telegram_id: str) -> bool:
    """Hapus user berdasarkan Telegram ID."""
    users = load_allowed_users()
    filtered = [u for u in users if u["telegram_id"] != telegram_id]
    if len(filtered) == len(users):
        return False
    save_allowed_users(filtered)
    return True


def promote_user(telegram_id: str) -> bool:
    """Naikkan user jadi admin."""
    users = load_allowed_users()
    updated = False
    for u in users:
        if u["telegram_id"] == telegram_id:
            u["role"] = "admin"
            updated = True
            break
    if updated:
        save_allowed_users(users)
    return updated


def dismiss_user(telegram_id: str) -> bool:
    """Turunkan admin jadi user biasa."""
    users = load_allowed_users()
    updated = False
    for u in users:
        if u["telegram_id"] == telegram_id:
            u["role"] = "user"
            updated = True
            break
    if updated:
        save_allowed_users(users)
    return updated


def get_all_allowed_users() -> list[dict]:
    """Ambil semua user dari JSON."""
    return load_allowed_users()
