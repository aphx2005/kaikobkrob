# -*- coding: utf-8 -*-
# ใช้ future annotations เพื่อให้ type hints อ้างอิงตัวเองได้ (ช่วยเวลาแยกไฟล์/คลาส)
from __future__ import annotations

# =========================
# Standard library (มาตรฐานของ Python)
# =========================
import os             # จัดการพาธไฟล์/โฟลเดอร์, เช็คมีไฟล์/โฟลเดอร์ไหม
import re             # ตรวจสอบ/จัดรูปแบบสตริงด้วย Regular Expression (เช่น validate อีเมล/เบอร์)
import shutil         # คัดลอก/ย้าย/ลบไฟล์หรือโฟลเดอร์ทั้งก้อน (เช่น ย้ายไฟล์รูปโปรไฟล์)
import sqlite3        # เชื่อมต่อฐานข้อมูล SQLite (users/products/orders/order_items)
from datetime import datetime   # เวลาปัจจุบัน, ตราประทับเวลา (เช่น สร้างเลขคิวรายวัน/เวลาชำระเงิน)
from pathlib import Path        # พาธเชิงวัตถุ (ข้ามแพลตฟอร์มได้ดี เช่น Windows/Unix)
from typing import Any, Dict, List, Optional, Tuple  # ประกาศชนิดข้อมูลให้โค้ดอ่านง่าย/ลดบั๊ก
import hashlib  # แฮชรหัสผ่านก่อนเก็บ
# =========================
# GUI & Dialog (ฝั่งหน้าจอผู้ใช้)
# =========================
import customtkinter as ctk             # UI หลัก (ธีมสวย ปรับสีมืด/สว่างได้)
from tkinter import filedialog, messagebox  # เปิดกล่องเลือกไฟล์/กล่องแจ้งเตือน

# =========================
# Imaging (จัดการรูปภาพ)
# =========================
from PIL import Image, ImageDraw  # เปิด/ย่อ/ครอปรูป (เช่น ครอปรูปโปรไฟล์ให้เป็นวงกลม)

# =========================
# PDF (ตัวเลือกเสริม: ออกรายงาน/ใบเสร็จ)
# - ห่อด้วย try เพื่อให้แอปรันได้แม้ไม่ได้ติดตั้ง reportlab
# =========================
try:
    from reportlab.pdfgen import canvas as pdf_canvas        # วาดเนื้อหา PDF ทีละจุด/เส้น/ข้อความ
    from reportlab.pdfbase import pdfmetrics                 # ลงทะเบียน/เรียกใช้ฟอนต์ใน PDF
    from reportlab.pdfbase.ttfonts import TTFont             # โหลดฟอนต์ TrueType (เช่น TH Sarabun)
    from reportlab.pdfbase.pdfmetrics import registerFontFamily  # จัด family ฟอนต์ normal/bold/italic
except Exception:
    pdf_canvas = None
    pdfmetrics = None
    TTFont = None
    registerFontFamily = None
# =========================================================
# ===============   DB UTILITIES / MODELS   ===============
# =========================================================
from pathlib import Path  # ถ้ายังไม่ได้ import

# ---- App paths ----
from pathlib import Path
# สร้างโฟลเดอร์ที่ต้องใช้ (กัน error เวลาเซฟไฟล์)
APP_DIR = Path(__file__).parent.resolve()
DB_FILE = APP_DIR / "app1.db"
ASSETS_DIR = APP_DIR / "assets"
RECEIPTS_DIR = APP_DIR / "receipts"
ASSETS_DIR.mkdir(exist_ok=True)
RECEIPTS_DIR.mkdir(exist_ok=True)

def db_connect() -> sqlite3.Connection:
    """
    เชื่อมต่อ SQLite:
    - เปิด foreign_keys ให้ใช้งานจริง
    - row_factory = Row เพื่ออ้างคอลัมน์ตามชื่อ
    """
    con = sqlite3.connect(str(DB_FILE))
    cur = con.cursor()
    try:
        cur.execute("PRAGMA foreign_keys=ON;")
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=NORMAL;")
    except Exception:
        pass
    con.row_factory = sqlite3.Row
    try:
        ensure_schema_migrations(con)
    except Exception:
        pass
    return con


# ---------- Password utils ----------
def _hash_password(pw: str) -> str:
    """แฮชรหัสผ่านด้วย SHA-256 (ควรมี salt ในระดับโปรดักชัน)"""
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()


def generate_daily_queue() -> str:
    """
    สร้างเลขคิวรายวันรูปแบบ K001, K002, ...
    - บันทึกตัวนับต่อวันใน queue_daily
    """
    today = datetime.now().strftime("%Y-%m-%d")

    with db_connect() as con:
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS queue_daily(
                queue_date  TEXT PRIMARY KEY,
                last_number INTEGER NOT NULL CHECK(last_number >= 0)
            )
        """)
        cur.execute("SELECT last_number FROM queue_daily WHERE queue_date = ?", (today,))
        row = cur.fetchone()

        if row:
            next_no = int(row["last_number"]) + 1
            cur.execute(
                "UPDATE queue_daily SET last_number = ? WHERE queue_date = ?",
                (next_no, today)
            )
        else:
            next_no = 1
            cur.execute(
                "INSERT INTO queue_daily(queue_date, last_number) VALUES (?, ?)",
                (today, next_no)
            )

    return f"K{next_no:03d}"


def init_db() -> None:
    """
    สร้างตารางหลัก + ดัชนี (ถ้ายังไม่มี):
    - users, products, orders, order_items, queue_daily
    - เพิ่ม CHECK/UNIQUE/FK ให้รัดกุม
    - seed ผู้ใช้ admin (ถ้ายังไม่มี) — เก็บรหัสผ่านแบบแฮช
    """
    with db_connect() as con:
        cur = con.cursor()

        # ---------- users ----------
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users(
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                username     TEXT NOT NULL UNIQUE,
                password     TEXT NOT NULL,                 -- เก็บเป็นแฮช
                full_name    TEXT,
                email        TEXT NOT NULL UNIQUE,
                phone        TEXT NOT NULL UNIQUE,
                profile_pic  TEXT,
                role         TEXT NOT NULL,                 -- 'admin' / 'customer'
                created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ---------- products ----------
        cur.execute("""
            CREATE TABLE IF NOT EXISTS products(
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                description TEXT,
                price       REAL NOT NULL CHECK(price >= 0),
                stock       INTEGER NOT NULL DEFAULT 0 CHECK(stock >= 0),
                category    TEXT,
                image_path  TEXT
            )
        """)

        # ---------- orders ----------
        cur.execute("""
            CREATE TABLE IF NOT EXISTS orders(
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                queue_code       TEXT,                        -- เช่น 'K001'
                customer_name    TEXT,
                total_price      REAL NOT NULL CHECK(total_price >= 0),
                paid_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
                receipt_pdf_path TEXT,                        -- เก็บพาธใบเสร็จ PDF
                slip_path        TEXT                         -- เก็บพาธสลิปโอน
            )
        """)

        # ---------- order_items ----------
        cur.execute("""
            CREATE TABLE IF NOT EXISTS order_items(
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id    INTEGER NOT NULL,
                product_id  INTEGER NOT NULL,
                qty         INTEGER NOT NULL CHECK(qty > 0),
                unit_price  REAL NOT NULL CHECK(unit_price >= 0),
                line_total  REAL NOT NULL CHECK(line_total >= 0),
                FOREIGN KEY(order_id)   REFERENCES orders(id)   ON DELETE CASCADE,
                FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE RESTRICT
            )
        """)

        # ---------- queue_daily ----------
        cur.execute("""
            CREATE TABLE IF NOT EXISTS queue_daily(
                queue_date  TEXT PRIMARY KEY,                 -- 'YYYY-MM-DD'
                last_number INTEGER NOT NULL CHECK(last_number >= 0)
            )
        """)

        # ---------- Indexes (ช่วยค้นไวขึ้น) ----------
        cur.execute("CREATE INDEX IF NOT EXISTS idx_products_category ON products(category)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_paid_at ON orders(paid_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_order_items_product ON order_items(product_id)")

        # ---------- seed admin ----------
        cur.execute("SELECT COUNT(*) AS c FROM users WHERE role = 'admin'")
        if int(cur.fetchone()["c"]) == 0:
            cur.execute(
                """
                INSERT INTO users(username, password, full_name, email, phone, role)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "admin",
                    _hash_password("Admin1234"),  # เดิมเป็น plain-text → ปรับเป็นแฮช
                    "Administrator",
                    "admin@example.com",
                    "0000000000",
                    "admin",
                ),
            )


def username_valid(u: str) -> Tuple[bool, str]:
    """Username ต้องไม่ว่าง และมี A–Z อย่างน้อย 1 ตัว"""
    if len(u) < 1:
        return False, "กรุณากรอก Username"
    if not re.search(r"[A-Z]", u):
        return False, "Username ต้องมีตัวอักษรภาษาอังกฤษพิมพ์ใหญ่อย่างน้อย 1 ตัว"
    return True, ""


def password_valid(pw: str) -> Tuple[bool, str]:
    """Password ต้องไม่ว่าง และมี A–Z อย่างน้อย 1 ตัว (แนะนำเพิ่มกฎความยาว/ตัวเลข/สัญลักษณ์)"""
    if len(pw) < 1:
        return False, "กรุณากรอก Password"
    if not re.search(r"[A-Z]", pw):
        return False, "Password ต้องมีตัวอักษรภาษาอังกฤษพิมพ์ใหญ่อย่างน้อย 1 ตัว"
    return True, ""


def register_user(
    username: str,
    password: str,
    full_name: str,
    email: str,
    phone: str,
    profile_pic_path: Optional[str],
) -> Tuple[bool, str]:
    """
    ลงทะเบียนผู้ใช้ใหม่:
    - ตรวจรูปแบบ/ค่าว่าง
    - เก็บรหัสผ่านแบบแฮช
    - จัด role เป็น 'customer' โดยอัตโนมัติ
    """
    ok_u, msg_u = username_valid(username)
    if not ok_u:
        return False, msg_u

    ok_p, msg_p = password_valid(password)
    if not ok_p:
        return False, msg_p

    if not full_name.strip():
        return False, "กรุณากรอกชื่อ-สกุล"
    if not email.strip():
        return False, "กรุณากรอกอีเมล"
    if not phone.strip():
        return False, "กรุณากรอกเบอร์โทร"

    try:
        with db_connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                INSERT INTO users(username, password, full_name, email, phone, profile_pic, role)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    username,
                    _hash_password(password),          # <-- แฮชก่อนเก็บ
                    full_name,
                    email,
                    phone,
                    profile_pic_path or None,
                    "customer",
                ),
            )
        return True, "สมัครสมาชิกสำเร็จแล้ว"
    except sqlite3.IntegrityError:
        return False, "ข้อมูลซ้ำ: โปรดตรวจสอบ Username/อีเมล/เบอร์โทร"
    except Exception as e:
        return False, f"เกิดข้อผิดพลาด: {e}"
# =========================================================
# ==========  AUTH: Register / Login / Reset  =============
# =========================================================

# NOTE: duplicate function renamed to avoid override
def register_user_v2_DISABLED(
    username: str,
    password: str,
    full_name: str,
    email: str,
    phone: str,
    profile_pic_path: Optional[str],
) -> Tuple[bool, str]:
    """
    สมัครสมาชิก:
    - ตรวจรูปแบบเบื้องต้น (username/password ต้องมีตัวใหญ่)
    - แก้ white-space ด้วย .strip() ทุกฟิลด์ที่เป็นข้อความ
    - เก็บรหัสผ่านแบบแฮช (SHA-256) แทน plain-text
    - กำหนด role เป็น 'customer'
    """
    # ---------- Validate ----------
    ok_u, msg_u = username_valid(username)
    if not ok_u:
        return False, msg_u

    ok_p, msg_p = password_valid(password)
    if not ok_p:
        return False, msg_p

    username = username.strip()
    password = password.strip()
    full_name = full_name.strip()
    email = email.strip()
    phone = phone.strip()

    if not full_name:
        return False, "กรุณากรอกชื่อ-สกุล"
    if not email:
        return False, "กรุณากรอกอีเมล"
    if not phone:
        return False, "กรุณากรอกเบอร์โทร"

    # ---------- Insert ----------
    try:
        with db_connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                INSERT INTO users(username, password, full_name, email, phone, role, profile_pic)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    username,
                    _hash_password(password),   # เก็บเป็นแฮช
                    full_name,
                    email,
                    phone,
                    "customer",
                    profile_pic_path or None,   # ถ้าไม่มีรูปให้เก็บเป็น NULL
                ),
            )
        return True, "สมัครสมาชิกสำเร็จ"
    except sqlite3.IntegrityError:
        # ชน UNIQUE (username/email/phone ซ้ำ)
        return False, "ข้อมูลซ้ำ (username / email / phone ถูกใช้แล้ว)"
    except Exception as e:
        return False, f"เกิดข้อผิดพลาด: {e}"


def try_login(username: str, password: str):
    import re
    hpw = _hash_password(password)

    with db_connect() as con:
        cur = con.cursor()
        # ดึงฟิลด์ที่ต้องใช้ในโปรไฟล์ให้ครบ
        cur.execute("""
            SELECT id, username, password, role, full_name, email, phone, profile_pic
            FROM users
            WHERE username=?
        """, (username,))
        row = cur.fetchone()
        if not row:
            return False, None

        uid, uname, stored, role, full_name, email, phone, profile_pic = row
        stored = stored or ""

        is_hash = bool(re.fullmatch(r"[0-9a-f]{64}", stored))
        ok = (stored == hpw) or (not is_hash and stored == password)
        if not ok:
            return False, None

        return True, {
            "id": uid,
            "username": uname,
            "role": role,
            "full_name": full_name,
            "email": email,
            "phone": phone,
            "profile_pic": profile_pic,
        }



def reset_password(
    username: str,
    full_name: str,
    email: str,
    phone: str,
    new_password: str,
) -> Tuple[bool, str]:
    """
    รีเซ็ตรหัส (เวอร์ชันตรวจหลายฟิลด์):
    - ต้องยืนยัน username / full_name / email / phone ให้ตรงกับ DB
    - ตรวจรูปแบบรหัสใหม่ แล้วเก็บเป็นแฮช
    """
    ok_p, msg_p = password_valid(new_password)
    if not ok_p:
        return False, msg_p

    username = username.strip()
    full_name = full_name.strip()
    email = email.strip()
    phone = phone.strip()
    new_password = new_password.strip()

    with db_connect() as con:
        cur = con.cursor()
        cur.execute(
            """
            SELECT id FROM users
            WHERE username = ? AND full_name = ? AND email = ? AND phone = ?
            """,
            (username, full_name, email, phone),
        )
        row = cur.fetchone()
        if not row:
            return False, "ข้อมูลไม่ตรงในระบบ"

        cur.execute(
            "UPDATE users SET password = ? WHERE id = ?",
            (_hash_password(new_password), row["id"]),   # อัปเดตเป็นแฮช
        )

    return True, "เปลี่ยนรหัสผ่านสำเร็จ"

def add_password_with_checkbox(parent, row, column=0, sticky="ew",
                               placeholder="Password", default_show=True):
    entry = ctk.CTkEntry(parent, height=36, placeholder_text=placeholder)  # 36 ให้เท่าช่องยูสเซอร์
    if default_show:
        entry.configure(show="•")
    entry.grid(row=row, column=column, sticky="ew",
               padx=0, pady=(0, 2))  # เอา padx=0 ให้กว้างเท่าช่องยูสเซอร์

    def _toggle():
        entry.configure(show="" if chk_var.get() == 1 else "•")

    chk_var = ctk.IntVar(value=0)
    chk = ctk.CTkCheckBox(parent, text="แสดงรหัสผ่าน",
                          variable=chk_var, command=_toggle)
    chk.grid(row=row+1, column=column, sticky="w",
             padx=0, pady=(0, 8))  # ให้ขอบเท่ากัน
    return entry, chk


# --- Lightweight schema migration helpers (safe to import multiple times) ---
def ensure_schema_migrations(conn):
    try:
        cur = conn.cursor()
        # Add customer_id to orders if missing
        cur.execute("PRAGMA table_info(orders);")
        cols = [r[1] for r in cur.fetchall()]
        if 'customer_id' not in cols:
            try:
                cur.execute("ALTER TABLE orders ADD COLUMN customer_id INTEGER;")
            except Exception:
                pass
            try:
                cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id);")
            except Exception:
                pass
        conn.commit()
    except Exception as e:
        # Do not raise in production UI; log if logger exists
        try:
            print('[migration] warning:', e)
        except Exception:
            pass


# --- Simple validators (centralized) ---
import re as _re

def is_valid_password(p: str) -> Tuple[bool, str]:
    if not p or len(p) < 8:
        return False, "รหัสผ่านต้องยาวอย่างน้อย 8 ตัวอักษร"
    if not _re.search(r"[A-Z]", p):
        return False, "รหัสผ่านต้องมีตัวพิมพ์ใหญ่อย่างน้อย 1 ตัว"
    if not _re.search(r"[a-z]", p):
        return False, "รหัสผ่านต้องมีตัวพิมพ์เล็กอย่างน้อย 1 ตัว"
    if not _re.search(r"[0-9]", p):
        return False, "รหัสผ่านต้องมีตัวเลขอย่างน้อย 1 ตัว"
    if not _re.search(r"[^A-Za-z0-9]", p):
        return False, "รหัสผ่านต้องมีอักขระพิเศษอย่างน้อย 1 ตัว"
    return True, ""

def is_valid_email(e: str) -> bool:
    return bool(e and _re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", e))

def is_valid_phone(ph: str) -> bool:
    return bool(ph and _re.match(r"^[0-9\-\+]{9,12}$", ph))


# =========================
# LOGIN
# =========================
class LoginPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app

        screen_w = getattr(self.app, "WIDTH", 1280)
        screen_h = getattr(self.app, "HEIGHT", 720)

        # พื้นหลังเฉพาะหน้า (เปลี่ยนชื่อไฟล์ได้)
        self._apply_fullscreen_background(screen_w, screen_h, "bg_login.png")

        # การ์ดกลาง
        self.card_frame = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        self.card_frame.place(relx=0.5, rely=0.60, anchor="center")
        self.card_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self.card_frame, text="เข้าสู่ระบบ",
                     text_color="black", font=ctk.CTkFont(size=20, weight="bold")
        ).grid(row=0, column=0, padx=24, pady=(12, 6), sticky="n")

        # ผู้ใช้
        ctk.CTkLabel(self.card_frame, text="ชื่อผู้ใช้", text_color="black")\
            .grid(row=1, column=0, padx=24, pady=(0, 4), sticky="w")
        self.ed_user = ctk.CTkEntry(self.card_frame, height=36)
        self.ed_user.grid(row=2, column=0, padx=24, pady=(0, 10), sticky="ew")

        # รหัสผ่าน
        ctk.CTkLabel(self.card_frame, text="รหัสผ่าน", text_color="black")\
            .grid(row=3, column=0, padx=24, pady=(0, 4), sticky="w")
        self.ed_pw = ctk.CTkEntry(self.card_frame, height=36, show="*")
        self.ed_pw.grid(row=4, column=0, padx=24, pady=(0, 6), sticky="ew")

        # แสดง/ซ่อนรหัส
        self.var_show_pw = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(self.card_frame, text="แสดงรหัสผ่าน",
                        variable=self.var_show_pw, command=self._toggle_pw,
                        checkbox_width=16, checkbox_height=16)\
            .grid(row=5, column=0, padx=24, pady=(0, 6), sticky="w")

        # ปุ่มเข้าสู่ระบบ
        ctk.CTkButton(self.card_frame, text="เข้าสู่ระบบ",
                      fg_color="#bcab2e", hover_color="#cf7f17", text_color="black",
                      command=self.on_login_click)\
            .grid(row=6, column=0, padx=24, pady=(4, 8), sticky="ew")

        # ลิงก์ไปสมัคร/ลืมรหัส
        links = ctk.CTkFrame(self.card_frame, fg_color="transparent")
        links.grid(row=7, column=0, padx=24, pady=(0, 6), sticky="ew")
        def _textlink(parent, text, cmd):
            return ctk.CTkButton(parent, text=text, command=cmd, width=0, height=24,
                                 fg_color="transparent", hover_color="#eeeeee",
                                 text_color="#1a73e8", corner_radius=4)
        _textlink(links, "สมัครสมาชิก", lambda: self.app.show_page("register")).pack(side="left")
        ctk.CTkLabel(links, text="  |  ", text_color="#666").pack(side="left")
        _textlink(links, "ลืมรหัสผ่าน", lambda: self.app.show_page("resetpw")).pack(side="left")

        # ข้อความเตือน
        self.message_label = ctk.CTkLabel(self.card_frame, text="", text_color="red")
        self.message_label.grid(row=8, column=0, padx=24, pady=(0, 4), sticky="w")

        # Enter = Login
        self.ed_pw.bind("<Return>", lambda e: self.on_login_click())

        # ปุ่มผู้จัดทำ (ถ้าไม่ต้องการลบได้)
        ctk.CTkButton(self, text="ผู้จัดทำ",
                      fg_color="transparent", hover_color="#444444",
                      border_width=1, border_color="white",
                      corner_radius=0, width=64, height=30,
                      text_color="white", font=ctk.CTkFont(size=10, weight="bold"),
                      command=lambda: self.app.show_page("info"))\
            .place(relx=1.0, rely=1.0, x=-20, y=-18, anchor="se")

    # helpers
    def _toggle_pw(self):
        self.ed_pw.configure(show="" if self.var_show_pw.get() else "*")

    def on_login_click(self):
        u = (self.ed_user.get() or "").strip()
        p = (self.ed_pw.get() or "").strip()
        ok, user = try_login(u, p)
        if not ok:
            messagebox.showerror("เข้าสู่ระบบ", "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
            return
        self.app.current_user = user or {}
        self.app.show_page("adminmenu" if (user or {}).get("role") == "admin" else "customermenu")

    def _apply_fullscreen_background(self, screen_w: int, screen_h: int, filename: str) -> None:
        from pathlib import Path
        base_dir = Path(__file__).parent.resolve()
        bg_path  = base_dir / "assets" / filename
        try:
            pil_bg = Image.open(bg_path).resize((screen_w, screen_h), Image.LANCZOS)
            self._bg_ref = ctk.CTkImage(light_image=pil_bg, dark_image=pil_bg, size=(screen_w, screen_h))
            ctk.CTkLabel(self, image=self._bg_ref, text="").place(relx=0, rely=0, relwidth=1, relheight=1)
        except Exception:
            self.configure(fg_color=("#f5f5f5", "#1a1a1a"))


# =========================
# REGISTER
# =========================
class RegisterPage(ctk.CTkFrame):
    """สมัครสมาชิก + อัปโหลดรูปโปรไฟล์ (ครอปวงกลม)"""
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app

        from pathlib import Path
        self.base_dir = Path(__file__).parent.resolve()

        screen_w = getattr(self.app, "WIDTH", 1280)
        screen_h = getattr(self.app, "HEIGHT", 720)

        self._apply_fullscreen_background(screen_w, screen_h, "bg1.png")

        self.profile_pic_path: Optional[str] = None
        self.preview_img_ref = None

        card_w = int(screen_w * 0.70)
        card_h = int(screen_h * 0.62)
        self.card = ctk.CTkFrame(self, fg_color="white", corner_radius=15, width=card_w, height=card_h)
        self.card.place(relx=0.5, rely=0.55, anchor="center")
        self.card.grid_propagate(False)

        inner = ctk.CTkFrame(self.card, fg_color="transparent")
        inner.pack(expand=True, fill="both", padx=40, pady=30)
        inner.grid_columnconfigure(0, weight=1)
        inner.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(inner, text="สมัครสมาชิก",
                     font=ctk.CTkFont(size=22, weight="bold"), text_color="black")\
            .grid(row=0, column=0, columnspan=2, pady=(0, 20))

        # รูปโปรไฟล์ + ปุ่มเลือก
        self.avatar_preview_lbl = ctk.CTkLabel(inner, text="", fg_color="transparent")
        self.avatar_preview_lbl.grid(row=1, column=0, sticky="e", pady=(0, 10), padx=(0, 10))
        ctk.CTkButton(inner, text="เลือกรูปโปรไฟล์...", width=140,
                      fg_color="#d9c24b", hover_color="#cf7f17", text_color="black",
                      corner_radius=8, command=self._choose_profile_pic)\
            .grid(row=1, column=1, sticky="w", pady=(0, 10), padx=(10, 0))

        # ช่องกรอก
        ctk.CTkLabel(inner, text="ชื่อ-สกุล", text_color="black",
                     font=ctk.CTkFont(size=13, weight="bold"))\
            .grid(row=2, column=0, sticky="w", pady=(10, 4), padx=(0, 10))
        self.fullname_entry = ctk.CTkEntry(inner, placeholder_text="ชื่อ-สกุล")
        self.fullname_entry.grid(row=2, column=1, sticky="ew", pady=(10, 4), padx=(0, 10))

        ctk.CTkLabel(inner, text="เบอร์โทร", text_color="black",
                     font=ctk.CTkFont(size=13, weight="bold"))\
            .grid(row=3, column=0, sticky="w", pady=(4, 4), padx=(0, 10))
        self.phone_entry = ctk.CTkEntry(inner, placeholder_text="เบอร์โทร")
        self.phone_entry.grid(row=3, column=1, sticky="ew", pady=(4, 4), padx=(0, 10))

        ctk.CTkLabel(inner, text="อีเมล", text_color="black",
                     font=ctk.CTkFont(size=13, weight="bold"))\
            .grid(row=4, column=0, sticky="w", pady=(4, 4), padx=(0, 10))
        self.email_entry = ctk.CTkEntry(inner, placeholder_text="example@email.com")
        self.email_entry.grid(row=4, column=1, sticky="ew", pady=(4, 4), padx=(0, 10))

        ctk.CTkLabel(inner, text="ชื่อผู้ใช้", text_color="black",
                     font=ctk.CTkFont(size=13, weight="bold"))\
            .grid(row=5, column=0, sticky="w", pady=(8, 4), padx=(0, 10))
        self.username_entry = ctk.CTkEntry(inner, placeholder_text="เป็นตัวอักษรภาษาอังกฤษ หรือ ตัวเลข")
        self.username_entry.grid(row=5, column=1, sticky="ew", pady=(8, 4), padx=(0, 10))

        ctk.CTkLabel(inner, text="รหัสผ่าน", text_color="black",
                     font=ctk.CTkFont(size=13, weight="bold"))\
            .grid(row=6, column=0, sticky="w", pady=(4, 4), padx=(0, 10))
        pw_row = ctk.CTkFrame(inner, fg_color="transparent")
        pw_row.grid(row=6, column=1, sticky="ew", pady=(4, 4), padx=(0, 10))
        pw_row.grid_columnconfigure(0, weight=1)
        self.password_entry = ctk.CTkEntry(pw_row, show="•", placeholder_text="ต้องมีตัวพิมพ์ใหญ่อย่างน้อย 1 ตัว")
        self.password_entry.grid(row=0, column=0, sticky="ew")

        ctk.CTkLabel(inner, text="ยืนยันรหัสผ่าน", text_color="black",
                     font=ctk.CTkFont(size=13, weight="bold"))\
            .grid(row=7, column=0, sticky="w", pady=(0, 35), padx=(0, 10))
        cpw_row = ctk.CTkFrame(inner, fg_color="transparent")
        cpw_row.grid(row=7, column=1, sticky="ew", pady=(0, 0), padx=(0, 10))
        cpw_row.grid_columnconfigure(0, weight=1)
        self.confirm_entry = ctk.CTkEntry(cpw_row, show="•", placeholder_text="พิมพ์รหัสผ่านซ้ำ")
        self.confirm_entry.grid(row=0, column=0, sticky="ew")

        self.show_pw_var = ctk.BooleanVar(value=False)
        def _toggle_both():
            show_char = "" if self.show_pw_var.get() else "•"
            self.password_entry.configure(show=show_char)
            self.confirm_entry.configure(show=show_char)
        ctk.CTkCheckBox(cpw_row, text="แสดงรหัสผ่าน",
                        variable=self.show_pw_var, command=_toggle_both,
                        checkbox_width=16, checkbox_height=16)\
            .grid(row=1, column=0, sticky="w", pady=(6, 0))

        # ปุ่ม
        btn_frame = ctk.CTkFrame(inner, fg_color="transparent")
        btn_frame.grid(row=8, column=0, columnspan=2, pady=(24, 0))
        ctk.CTkButton(btn_frame, text="สมัคร", width=120, height=36,
                      fg_color="#108a5a", hover_color="#0a5839",
                      text_color="white", corner_radius=8,
                      command=self._register_action)\
            .grid(row=0, column=0, padx=(0, 12))
        ctk.CTkButton(btn_frame, text="กลับ", width=120, height=36,
                      fg_color="#c41216", hover_color="#800000",
                      text_color="white", corner_radius=8,
                      command=lambda: self.app.show_page("login"))\
            .grid(row=0, column=1, padx=(12, 0))

        # label แจ้งเตือน
        self.msg_label = ctk.CTkLabel(inner, text="", text_color="#c41216",
                                      font=ctk.CTkFont(size=12), anchor="w", justify="left")
        self.msg_label.grid(row=9, column=0, columnspan=2, sticky="w", pady=(16, 0))

        # รูปเริ่มต้น
        self._set_avatar_preview_default()

        # Enter = สมัคร
        self._enter_binding_target = self.winfo_toplevel()
        self._enter_binding_target.bind("<Return>", lambda e: self._register_action())

    def destroy(self):
        try:
            if hasattr(self, "_enter_binding_target") and self._enter_binding_target:
                self._enter_binding_target.unbind("<Return>")
        except Exception:
            pass
        super().destroy()

    # Utilities (พื้นหลัง/รูป)
    def _apply_fullscreen_background(self, screen_w: int, screen_h: int, filename: str) -> None:
        bg_path = self.base_dir / "assets" / filename
        try:
            pil_bg = Image.open(bg_path).resize((screen_w, screen_h), Image.LANCZOS)
            self.bg_img_ref = ctk.CTkImage(light_image=pil_bg, dark_image=pil_bg, size=(screen_w, screen_h))
            ctk.CTkLabel(self, image=self.bg_img_ref, text="").place(relx=0, rely=0, relwidth=1, relheight=1)
        except Exception:
            self.configure(fg_color="#f7dc5a")

    def _choose_profile_pic(self) -> None:
        path = filedialog.askopenfilename(
            title="เลือกรูปโปรไฟล์",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.gif *.bmp")]
        )
        if not path: return
        save_dir = self.base_dir / "user_pics"
        save_dir.mkdir(exist_ok=True)
        new_name = f"profile_{int(datetime.now().timestamp())}.png"
        final_path = save_dir / new_name
        try:
            pil_img = Image.open(path).convert("RGBA").resize((100, 100), Image.LANCZOS)
            mask = Image.new("L", (100, 100), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, 100, 100), fill=255)
            pil_img.putalpha(mask)
            pil_img.save(final_path)
        except Exception:
            self.msg_label.configure(text="อัปโหลดรูปไม่สำเร็จ", text_color="#c41216")
            return
        self.profile_pic_path = str(final_path)
        self._update_avatar_preview(final_path)

    def _set_avatar_preview_default(self) -> None:
        fallback_path = self.base_dir / "assets" / "avatar_chicken.png"
        self._update_avatar_preview(fallback_path)

    def _update_avatar_preview(self, img_path) -> None:
        try:
            pil_img = Image.open(img_path).convert("RGBA").resize((80, 80), Image.LANCZOS)
            mask = Image.new("L", (80, 80), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, 80, 80), fill=255)
            pil_img.putalpha(mask)
        except Exception:
            pil_img = Image.new("RGBA", (80, 80), (196, 18, 22, 255))
        self.preview_img_ref = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(80, 80))
        self.avatar_preview_lbl.configure(image=self.preview_img_ref, text="")

    # Validate + บันทึก DB
    def _register_action(self) -> None:
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        confirm  = self.confirm_entry.get().strip()
        full     = self.fullname_entry.get().strip()
        phone    = self.phone_entry.get().strip()
        email    = self.email_entry.get().strip()

        if password != confirm:
            self.msg_label.configure(text="รหัสผ่านทั้งสองช่องไม่ตรงกัน", text_color="#c41216")
            return

        ok, msg = register_user(
            username=username, password=password, full_name=full,
            email=email, phone=phone, profile_pic_path=self.profile_pic_path,
        )
        if not ok:
            self.msg_label.configure(text=msg, text_color="#c41216")
            return

        # success
        for e in (self.username_entry, self.password_entry, self.confirm_entry,
                  self.fullname_entry, self.phone_entry, self.email_entry):
            e.delete(0, "end")
        self.profile_pic_path = None
        self._set_avatar_preview_default()
        self.msg_label.configure(text="สมัครสมาชิกสำเร็จแล้ว ✔", text_color="#108a5a")


# =========================
# RESET PASSWORD
# =========================
class ResetPasswordPage(ctk.CTkFrame):
    """รีเซ็ตรหัสผ่านด้วยอีเมลเดียว + ตรวจ rule + เข้ารหัส"""
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app

        screen_w = getattr(self.app, "WIDTH", 1280)
        screen_h = getattr(self.app, "HEIGHT", 720)

        self._apply_fullscreen_background(screen_w, screen_h, "bg1.png")

        card_w = min(max(int(screen_w * 0.40), 420), 560)
        card_h = min(max(int(screen_h * 0.45), 340), 480)

        card = ctk.CTkFrame(self, fg_color="white", corner_radius=15, width=card_w, height=card_h)
        card.place(relx=0.5, rely=0.55, anchor="center")
        card.grid_propagate(False)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(expand=True, fill="both", padx=80, pady=40)
        inner.grid_columnconfigure(0, weight=1)
        inner.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(inner, text="ลืมรหัสผ่าน",
                     font=ctk.CTkFont(size=28, weight="bold"), text_color="black")\
            .grid(row=0, column=0, columnspan=2, pady=(10, 30))

        ctk.CTkLabel(inner, text="อีเมลที่ใช้สมัคร", text_color="black")\
            .grid(row=1, column=0, sticky="w", pady=5)
        self.email_entry = ctk.CTkEntry(inner, placeholder_text="example@email.com")
        self.email_entry.grid(row=1, column=1, sticky="ew", pady=5)

        ctk.CTkLabel(inner, text="ตั้งรหัสผ่านใหม่", text_color="black")\
            .grid(row=2, column=0, sticky="w", pady=5)
        pw_row = ctk.CTkFrame(inner, fg_color="transparent")
        pw_row.grid(row=2, column=1, sticky="ew", pady=5)
        pw_row.grid_columnconfigure(0, weight=1)
        self.new_pw_entry = ctk.CTkEntry(pw_row, show="•", placeholder_text="Password (มีตัวพิมพ์ใหญ่ 1 ตัวขึ้นไป)")
        self.new_pw_entry.grid(row=0, column=0, sticky="ew")

        ctk.CTkLabel(inner, text="ยืนยันรหัสผ่านใหม่", text_color="black")\
            .grid(row=3, column=0, sticky="w", pady=5)
        cpw_row = ctk.CTkFrame(inner, fg_color="transparent")
        cpw_row.grid(row=3, column=1, sticky="ew", pady=5)
        cpw_row.grid_columnconfigure(0, weight=1)
        self.confirm_pw_entry = ctk.CTkEntry(cpw_row, show="•", placeholder_text="พิมพ์รหัสผ่านซ้ำ")
        self.confirm_pw_entry.grid(row=0, column=0, sticky="ew")

        # ติ๊กเดียว คุมสองช่อง
        self.show_pw_var = ctk.BooleanVar(value=False)
        def _toggle_both():
            show_char = "" if self.show_pw_var.get() else "•"
            self.new_pw_entry.configure(show=show_char)
            self.confirm_pw_entry.configure(show=show_char)
        ctk.CTkCheckBox(cpw_row, text="แสดงรหัสผ่าน",
                        variable=self.show_pw_var, command=_toggle_both,
                        checkbox_width=16, checkbox_height=16)\
            .grid(row=1, column=0, sticky="w", pady=(6, 0))

        # ปุ่ม
        btn_frame = ctk.CTkFrame(inner, fg_color="transparent")
        btn_frame.grid(row=4, column=0, columnspan=2, pady=(40, 0))
        ctk.CTkButton(btn_frame, text="รีเซ็ตรหัส",
                      width=140, height=40, fg_color="#108a5a", hover_color="#0a5839",
                      command=self.reset_action).grid(row=0, column=0, padx=10)
        ctk.CTkButton(btn_frame, text="กลับ",
                      width=140, height=40, fg_color="#c41216", hover_color="#800000",
                      command=lambda: self.app.show_page("login")).grid(row=0, column=1, padx=10)

        # Enter = ยืนยัน
        self._enter_binding_target = self.winfo_toplevel()
        self._enter_binding_target.bind("<Return>", lambda _e: self.reset_action())

    def destroy(self):
        try:
            if getattr(self, "_enter_binding_target", None):
                self._enter_binding_target.unbind("<Return>")
        except Exception:
            pass
        super().destroy()

    # Utilities
    def _apply_fullscreen_background(self, screen_w: int, screen_h: int, filename: str) -> None:
        from pathlib import Path
        base_dir = Path(__file__).parent.resolve()
        bg_path = base_dir / "assets" / filename
        try:
            pil_bg = Image.open(bg_path).resize((screen_w, screen_h), Image.LANCZOS)
            self.bg_img_ref = ctk.CTkImage(light_image=pil_bg, dark_image=pil_bg, size=(screen_w, screen_h))
            ctk.CTkLabel(self, image=self.bg_img_ref, text="").place(relx=0, rely=0, relwidth=1, relheight=1)
        except Exception:
            self.configure(fg_color="#f7dc5a")

    # Action
    def reset_action(self) -> None:
        email = self.email_entry.get().strip()
        new_pw = self.new_pw_entry.get().strip()
        confirm_pw = self.confirm_pw_entry.get().strip()

        if not email or not new_pw or not confirm_pw:
            messagebox.showerror("ผิดพลาด", "กรุณากรอกข้อมูลให้ครบ")
            return
        if new_pw != confirm_pw:
            messagebox.showerror("ผิดพลาด", "รหัสผ่านใหม่ทั้งสองช่องไม่ตรงกัน")
            return

        ok_pw, msg_pw = password_valid(new_pw)
        if not ok_pw:
            messagebox.showerror("ผิดพลาด", msg_pw)
            return

        with db_connect() as con:
            cur = con.cursor()
            cur.execute("SELECT id FROM users WHERE email = ?", (email,))
            row = cur.fetchone()
            if not row:
                messagebox.showerror("ผิดพลาด", "ไม่พบบัญชีที่ใช้อีเมลนี้")
                return
            cur.execute("UPDATE users SET password = ? WHERE id = ?",
                        (_hash_password(new_pw), row["id"]))
        messagebox.showinfo("สำเร็จ", "เปลี่ยนรหัสผ่านเรียบร้อยแล้ว")
        self.app.show_page("login")

class InfoPage(ctk.CTkFrame):
    """
    หน้าผู้จัดทำ / ข้อมูลโครงการ
    - พื้นหลังเต็มจอจาก assets/info.png
    - ปุ่มย้อนกลับมุมขวาล่าง
    """
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app

        # --- ขนาดจาก App (รองรับไม่มีด้วย getattr) ---
        screen_w = getattr(self.app, "WIDTH", 1280)
        screen_h = getattr(self.app, "HEIGHT", 720)

        # --- โหลดภาพพื้นหลัง ---
        self._apply_fullscreen_background(screen_w, screen_h)

        # --- ปุ่มย้อนกลับมุมขวาล่าง ---
        back_btn = ctk.CTkButton(
            self,
            text="ย้อนกลับ",
            fg_color="#c41216",
            hover_color="#800000",
            text_color="white",
            corner_radius=6,
            width=110,
            height=34,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=lambda: self.app.show_page("login"),
        )
        back_btn.place(relx=1.0, rely=1.0, x=-20, y=-20, anchor="se")

    # -----------------------------------------
    # Utilities
    # -----------------------------------------
    def _apply_fullscreen_background(self, screen_w: int, screen_h: int) -> None:
        """โหลดภาพ info.png เป็นพื้นหลัง (ล้มเหลว → ใช้สีเหลือง fallback)"""
        from pathlib import Path

        base_dir = Path(__file__).parent.resolve()
        bg_path = base_dir / "assets" / "info.png"

        try:
            pil_bg = Image.open(bg_path).resize((screen_w, screen_h), Image.LANCZOS)
            self.bg_img_ref = ctk.CTkImage(
                light_image=pil_bg,
                dark_image=pil_bg,
                size=(screen_w, screen_h)
            )
            ctk.CTkLabel(self, image=self.bg_img_ref, text="").place(
                relx=0, rely=0, relwidth=1, relheight=1
            )
        except (FileNotFoundError, OSError):
            # ถ้าโหลดรูปไม่ได้ → ใช้สีพื้นหลังแบบ fallback
            self.configure(fg_color="#f7dc5a")



# ===== helper นอกคลาส (อยู่นอก ProfilePage) =====
def load_user_by_id(user_id: int) -> dict | None:
    with db_connect() as con:
        cur = con.cursor()
        cur.execute("""
            SELECT id, username, role, full_name, email, phone, profile_pic
            FROM users WHERE id=?
        """, (user_id,))
        r = cur.fetchone()
        if not r:
            return None
        return {
            "id": r[0], "username": r[1], "role": r[2],
            "full_name": r[3], "email": r[4], "phone": r[5],
            "profile_pic": r[6],
        }


class ProfilePage(ctk.CTkFrame):
    """
    โหมดสองสถานะ:
    - View: ช่องถูกปิด, ปุ่มหลักเป็น 'แก้ไข', ปุ่มเลือกรูปถูกซ่อน
    - Edit: ช่องเปิดแก้ได้, แสดงปุ่ม 'เลือกรูปภาพ', ปุ่มหลักเป็น 'บันทึกข้อมูล'
    เลย์เอาต์: ซ้าย = รูปใหญ่ + ปุ่มเลือกรูป / ขวา = ชื่อ-สกุล, เบอร์, อีเมล + ปุ่ม
    """
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self._edit_mode = False

        # --- ขนาดจอ & BG ---
        sw = getattr(self.app, "WIDTH", 1280)
        sh = getattr(self.app, "HEIGHT", 720)
        self._apply_fullscreen_background(sw, sh)

        # --- การ์ดหลัก (ใหญ่ขึ้น) ---
        card_w = int(sw * 0.92)
        card_h = int(sh * 0.88)
        self.card = ctk.CTkFrame(self, fg_color="white", corner_radius=22, width=card_w, height=card_h)
        self.card.place(relx=0.5, rely=0.5, anchor="center")
        self.card.grid_propagate(False)

        # กริด 2 คอลัมน์
        self.card.grid_columnconfigure(0, weight=1, uniform="cols")
        self.card.grid_columnconfigure(1, weight=1, uniform="cols")
        self.card.grid_rowconfigure(1, weight=1)

        # หัวเรื่อง
        ctk.CTkLabel(self.card, text="โปรไฟล์ของฉัน", text_color="black",
                     font=ctk.CTkFont(size=24, weight="bold"))\
            .grid(row=0, column=0, columnspan=2, sticky="w", padx=28, pady=(22, 6))

        # ================= ซ้าย: รูป + ปุ่มเลือกรูป =================
        left = ctk.CTkFrame(self.card, fg_color="transparent")
        left.grid(row=1, column=0, sticky="nsew", padx=(28, 14), pady=(8, 12))
        left.grid_columnconfigure(0, weight=1)

        self._avatar_size_preview = 260  # แสดง
        self._avatar_size_save    = 300  # ไฟล์ที่จะบันทึก

        self.avatar_preview_img = None
        self.avatar_preview_lbl = ctk.CTkLabel(left, text="", fg_color="transparent")
        self.avatar_preview_lbl.grid(row=0, column=0, sticky="n", pady=(4, 16))

        # ปุ่ม 'เลือกรูปภาพ' (ซ่อนในโหมด View)
        self.btn_pick = ctk.CTkButton(
            left, text="เลือกรูปภาพ", fg_color="#108a5a", hover_color="#0a5839",
            text_color="white", corner_radius=12, width=180, height=40,
            command=self._change_pic
        )
        self.btn_pick.grid(row=1, column=0, sticky="n", pady=(0, 10))

        # ตัวเว้นยืด
        left.grid_rowconfigure(2, weight=1)

        # ================= ขวา: ฟอร์มข้อมูล =================
        right = ctk.CTkFrame(self.card, fg_color="transparent")
        right.grid(row=1, column=1, sticky="nsew", padx=(14, 28), pady=(8, 12))
        right.grid_columnconfigure(0, weight=1)
        lblf = ctk.CTkFont(size=16, weight="bold")

        ctk.CTkLabel(right, text="ชื่อ-สกุล", text_color="black", font=lblf)\
            .grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.ed_name = ctk.CTkEntry(right, height=46)
        self.ed_name.grid(row=1, column=0, sticky="ew", pady=(0, 14))

        ctk.CTkLabel(right, text="เบอร์โทร", text_color="black", font=lblf)\
            .grid(row=2, column=0, sticky="w", pady=(0, 6))
        self.ed_phone = ctk.CTkEntry(right, height=46, placeholder_text="0812345678")
        self.ed_phone.grid(row=3, column=0, sticky="ew", pady=(0, 14))

        ctk.CTkLabel(right, text="อีเมลล์", text_color="black", font=lblf)\
            .grid(row=4, column=0, sticky="w", pady=(0, 6))
        self.ed_email = ctk.CTkEntry(right, height=46, placeholder_text="example@email.com")
        self.ed_email.grid(row=5, column=0, sticky="ew", pady=(0, 14))

        right.grid_rowconfigure(6, weight=1)

        # ----- ปุ่มแก้ไข/บันทึก (ย้ายไปตำแหน่งตามกรอบเขียว) -----
        self.btn_edit_or_save = ctk.CTkButton(
            self.card,
            text="แก้ไข",
            fg_color="#c41216",          # ✅ สีแดง
            hover_color="#800000",
            text_color="white",
            corner_radius=18,
            height=48,
            width=180,
            command=self._toggle_edit_mode
        )

        # ✅ ตำแหน่งใหม่ตามกรอบเขียว
        self.btn_edit_or_save.place(relx=0.9, rely=0.55, anchor="center")


        # ปุ่มย้อนกลับมุมขวาล่างของการ์ด
        self.btn_back = ctk.CTkButton(
            self.card, text="ย้อนกลับ", fg_color="#c41216", hover_color="#800000",
            text_color="white", corner_radius=18, height=44, width=160,
            command=lambda: self.app.show_page("customermenu")
        )
        self.btn_back.grid(row=2, column=1, sticky="e", padx=28, pady=(0, 22))

        # สถานะสั้น ๆ ใกล้ปุ่มหลัก
        self.msg_label = ctk.CTkLabel(self.card, text="", text_color="#108a5a",
                                      font=ctk.CTkFont(size=13))
        self.msg_label.grid(row=2, column=0, sticky="w", padx=28, pady=(0, 22))

        # โหลดข้อมูล/รูปครั้งแรก + ตั้งเป็นโหมด View
        self._set_preview_avatar()
        self.refresh()
        self._apply_view_mode_ui()

    # ---------- BG ----------
    def _apply_fullscreen_background(self, w: int, h: int) -> None:
        from pathlib import Path
        base_dir = Path(__file__).parent.resolve()
        bg_path = base_dir / "assets" / "bg_0.png"
        try:
            pil_bg = Image.open(bg_path).resize((w, h), Image.LANCZOS)
            self._bg_ref = ctk.CTkImage(light_image=pil_bg, dark_image=pil_bg, size=(w, h))
            ctk.CTkLabel(self, image=self._bg_ref, text="").place(relx=0, rely=0, relwidth=1, relheight=1)
        except Exception:
            self.configure(fg_color="#f7dc5a")

    # ---------- โหมด/การสลับ ----------
    def _apply_view_mode_ui(self):
        for e in (self.ed_name, self.ed_phone, self.ed_email):
            e.configure(state="disabled")

        self.btn_pick.grid_remove()

        self.btn_edit_or_save.configure(
            text="แก้ไข",
            fg_color="#c41216",      # ✅ สีแดงตอนเป็นปกติ
            hover_color="#800000",
            command=self._toggle_edit_mode
        )


    def _apply_edit_mode_ui(self):
        for e in (self.ed_name, self.ed_phone, self.ed_email):
            e.configure(state="normal")

        self.btn_pick.grid()

        self.btn_edit_or_save.configure(
            text="บันทึกข้อมูล",
            fg_color="#108a5a",       # ✅ สีเขียวในโหมดบันทึก
            hover_color="#0a5839",
            command=self._save_then_view
        )


    def _toggle_edit_mode(self):
        self._edit_mode = True
        self._apply_edit_mode_ui()
        self.msg_label.configure(text="")

    def _save_then_view(self):
        if self._save_profile():
            self._edit_mode = False
            self._apply_view_mode_ui()

    # ---------- ภาพโปรไฟล์ ----------
    def _set_preview_avatar(self) -> None:
        from pathlib import Path
        base_dir = Path(__file__).parent.resolve()
        img_path = None
        if self.app.current_user:
            img_path = self.app.current_user.get("profile_pic")
        if not img_path or not Path(img_path).exists():
            img_path = base_dir / "assets" / "avatar_chicken.png"

        try:
            S = self._avatar_size_preview
            pil = Image.open(img_path).convert("RGBA").resize((S, S), Image.LANCZOS)
            mask = Image.new("L", (S, S), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, S, S), fill=255)
            pil.putalpha(mask)
        except Exception:
            S = self._avatar_size_preview
            pil = Image.new("RGBA", (S, S), (196, 18, 22, 255))

        self.avatar_preview_img = ctk.CTkImage(light_image=pil, dark_image=pil, size=(S, S))
        self.avatar_preview_lbl.configure(image=self.avatar_preview_img, text="")

    def _change_pic(self) -> None:
        path = filedialog.askopenfilename(
            title="เลือกรูปโปรไฟล์",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.gif *.bmp")]
        )
        if not path:
            return
        from pathlib import Path
        base_dir = Path(__file__).parent.resolve()
        save_dir = base_dir / "user_pics"
        save_dir.mkdir(exist_ok=True)
        final_path = save_dir / f"profile_{int(datetime.now().timestamp())}.png"
        try:
            S = self._avatar_size_save
            pil = Image.open(path).convert("RGBA").resize((S, S), Image.LANCZOS)
            mask = Image.new("L", (S, S), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, S, S), fill=255)
            pil.putalpha(mask)
            pil.save(final_path)
        except Exception:
            self.msg_label.configure(text="อัปโหลดรูปไม่สำเร็จ", text_color="red")
            return

        # อัปเดต DB + session และรีเฟรชแถบหัว/พรีวิว
        self._update_user_fields_in_db({"profile_pic": str(final_path)})
        self._set_preview_avatar()
        self.msg_label.configure(text="อัปโหลดรูปแล้ว ✔", text_color="#108a5a")
        for key in ("customermenu", "basket"):
            page = self.app.pages.get(key)
            if page and hasattr(page, "profile_header"):
                page.profile_header.refresh()

    # ---------- DB helpers ----------
    def _update_user_fields_in_db(self, updates: dict) -> bool:
        if not self.app.current_user:
            return False
        uid = self.app.current_user.get("id")
        if uid is None:
            return False
        allow = {"full_name", "email", "phone", "profile_pic"}
        fields = [k for k in updates.keys() if k in allow]
        if not fields:
            return False
        set_clause = ", ".join(f"{f}=?" for f in fields)
        params = [updates[f] for f in fields] + [uid]
        try:
            with db_connect() as con:
                con.execute(f"UPDATE users SET {set_clause} WHERE id=?", params)
            for f in fields:
                self.app.current_user[f] = updates[f]
            return True
        except sqlite3.IntegrityError:
            self.msg_label.configure(text="อีเมลหรือเบอร์โทรซ้ำกับผู้ใช้อื่น", text_color="red")
            return False
        except Exception as e:
            self.msg_label.configure(text=f"บันทึกไม่สำเร็จ: {e}", text_color="red")
            return False

    # ---------- lifecycle ----------
    def refresh(self) -> None:
        # ถ้า session ไม่มี email/phone ให้ดึงจาก DB แล้วเติม
        u = self.app.current_user or {}
        if u and (not u.get("email") or not u.get("phone")):
            loaded = load_user_by_id(u.get("id"))
            if loaded:
                self.app.current_user.update(loaded)
                u = self.app.current_user

        # เติมค่าลงช่อง
        self.ed_name.configure(state="normal");  self.ed_name.delete(0, "end");  self.ed_name.insert(0, u.get("full_name", "")); self.ed_name.configure(state="disabled")
        self.ed_phone.configure(state="normal"); self.ed_phone.delete(0, "end"); self.ed_phone.insert(0, u.get("phone", ""));     self.ed_phone.configure(state="disabled")
        self.ed_email.configure(state="normal"); self.ed_email.delete(0, "end"); self.ed_email.insert(0, u.get("email", ""));     self.ed_email.configure(state="disabled")

        self._set_preview_avatar()
        self.msg_label.configure(text="")

    # ---------- save ----------
    def _save_profile(self) -> bool:
        updates = {
            "full_name": self.ed_name.get().strip(),
            "email":     self.ed_email.get().strip(),
            "phone":     self.ed_phone.get().strip(),
        }
        ok = self._update_user_fields_in_db(updates)
        if ok:
            self.msg_label.configure(text="บันทึกข้อมูลเรียบร้อย ✔", text_color="#108a5a")
            # รีเฟรช header ถ้ามี
            for key in ("customermenu", "basket"):
                page = self.app.pages.get(key)
                if page and hasattr(page, "profile_header"):
                    page.profile_header.refresh()
        return ok



class ProfileHeader(ctk.CTkFrame):
    """
    แถบมุมซ้ายบนของทุกหน้าลูกค้า:
    - avatar วงกลม (กดแล้วไปหน้าโปรไฟล์)
    - "User: ชื่อ" (ถ้ามี full_name ใช้อันนั้นก่อน)
    """

    def __init__(self, master, app):
        super().__init__(master, fg_color="#ffde59")  # ธีมเดิม (เหลือง)
        self.app = app
        self.avatar_img_ref = None  # กัน GC

        # โหลดรูปครั้งแรกเพื่อใส่ให้ปุ่ม
        self._reload_avatar_image()

        # ปุ่ม avatar
        self.avatar_btn = ctk.CTkButton(
            self,
            text="",
            width=50,
            height=50,
            corner_radius=0,
            fg_color="#ffde59",
            hover_color="#ffffff",
            image=self.avatar_img_ref,
            command=self._goto_profile,
        )
        self.avatar_btn.grid(row=0, column=0, sticky="w")

        # label ชื่อ user
        display_name = "-"
        if self.app.current_user:
            full = self.app.current_user.get("full_name")
            usern = self.app.current_user.get("username")
            display_name = full if full else (usern if usern else "-")

        self.name_label = ctk.CTkLabel(
            self,
            text=f"User: {display_name}",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="black",
            fg_color="#ffde59",
        )
        self.name_label.grid(row=0, column=1, sticky="w", padx=(10, 0))

        # layout ป้องกันบีบ
        self.grid_columnconfigure(0, minsize=50)
        self.grid_columnconfigure(1, weight=1)

    def refresh(self):
        """
        เรียกทุกครั้งก่อนโชว์หน้า:
        - อัปเดตชื่อ
        - รีโหลดรูป (กรณีผู้ใช้เปลี่ยนรูปใหม่)
        """
        display_name = "-"
        if self.app.current_user:
            full = self.app.current_user.get("full_name")
            usern = self.app.current_user.get("username")
            display_name = full if full else (usern if usern else "-")

        self.name_label.configure(text=f"User: {display_name}")

        # อัปเดตรูปใหม่
        self._reload_avatar_image()
        self.avatar_btn.configure(image=self.avatar_img_ref)

    def _goto_profile(self):
        """เมื่อกดรูป → ไปหน้าโปรไฟล์"""
        self.app.show_page("profile")

    def _reload_avatar_image(self):
        """
        โหลดรูปโปรไฟล์ล่าสุด:
        - ถ้ามี self.app.current_user['profile_pic'] และไฟล์ยังอยู่ → ใช้อันนั้น
        - ถ้าไม่มีก็ใช้ assets/avatar_chicken.png
        - ครอปเป็นวงกลมขนาด 50x50
        """
        from pathlib import Path
        base_dir = Path(__file__).parent.resolve()

        img_path = None
        if self.app.current_user:
            pic = self.app.current_user.get("profile_pic")
            if pic and Path(pic).exists():
                img_path = Path(pic)

        if img_path is None:
            img_path = base_dir / "assets" / "avatar_chicken.png"

        try:
            pil_avatar = Image.open(img_path).convert("RGBA").resize((50, 50), Image.LANCZOS)
            mask = Image.new("L", (50, 50), 0)
            d = ImageDraw.Draw(mask)
            d.ellipse((0, 0, 50, 50), fill=255)
            pil_avatar.putalpha(mask)
        except (FileNotFoundError, OSError, ValueError):
            # fallback สุดท้าย: สี่เหลี่ยมแดง
            pil_avatar = Image.new("RGBA", (50, 50), (196, 18, 22, 255))

        self.avatar_img_ref = ctk.CTkImage(light_image=pil_avatar, dark_image=pil_avatar, size=(50, 50))


class CustomerMenuPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app

        # --- ขนาดจอครั้งเดียว ---
        screen_w = getattr(self.app, "WIDTH", 1280)
        screen_h = getattr(self.app, "HEIGHT", 720)

        # --- พื้นหลังเต็มจอ ---
        self._apply_fullscreen_background(screen_w, screen_h, filename="menu.png")

        # ======================================================
        # ปุ่มหมวดหมู่ + ปุ่มตะกร้า (ลอยบนพื้นหลัง)
        # ======================================================

        # Header ผู้ใช้มุมซ้ายบน
        self.profile_header = ProfileHeader(self, self.app)
        self.profile_header.place(x=20, y=20, anchor="nw")
        self.profile_header.refresh()

        # ปุ่มตะกร้า (ลอยขวาบน)
        from pathlib import Path
        base_dir = Path(__file__).parent.resolve()
        top_cart_path = base_dir / "assets" / "icon_cart.png"
        try:
            pil_cart_top = Image.open(top_cart_path).resize((96, 96), Image.LANCZOS)
            self.cart_img_ref_top = ctk.CTkImage(light_image=pil_cart_top, dark_image=pil_cart_top, size=(96, 96))
        except (FileNotFoundError, OSError, ValueError):
            self.cart_img_ref_top = None

        self.cart_btn = ctk.CTkButton(
            self,
            width=55,
            height=32,
            corner_radius=0,
            fg_color="#ffde59",
            hover_color="#ffde59",
            text="ตะกร้า" if self.cart_img_ref_top is None else "",
            image=self.cart_img_ref_top,
            text_color="white",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=lambda: self.app.show_page("basket"),
        )
        self.cart_btn.place(relx=1.0, y=25, x=-27, anchor="ne")

        # แถบปุ่มหมวดหมู่
        self.cat_bar = ctk.CTkFrame(self, fg_color="transparent")
        self.cat_bar.place(x=40, y=115, anchor="nw")  # ปรับระดับเมนูบาร์

        def make_cat_btn(cat_text: str):
            return ctk.CTkButton(
                self.cat_bar,
                text=cat_text,
                height=24,
                width=90,
                corner_radius=6,
                fg_color="black",
                hover_color="#333333",
                text_color="white",
                font=ctk.CTkFont(size=12, weight="bold"),
                command=lambda c=cat_text: self._switch_category(c),
            )

        for i, cat in enumerate(["All", "Combo", "Set", "Beverage"]):
            make_cat_btn(cat).grid(row=0, column=i, padx=4, pady=4)

        # ======================================================
        # กล่องรายการสินค้า (กรอบเทาอ่อน + scroll)
        # ======================================================
        box_w = int(screen_w * 0.85)
        box_h = int(screen_h * 0.7)

        wrapper = ctk.CTkFrame(self, fg_color="#efefef", corner_radius=10, width=box_w, height=box_h)
        wrapper.place(relx=0.5, rely=0.55, anchor="center")
        wrapper.grid_propagate(False)
        wrapper.grid_rowconfigure(0, weight=1)
        wrapper.grid_columnconfigure(0, weight=1)

        self.items_scroll = ctk.CTkScrollableFrame(
            wrapper,
            fg_color="#efefef",
            corner_radius=6,
            width=box_w - 40,
            height=box_h - 40,
        )
        self.items_scroll.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)

        # ---------- ปุ่มย้อนกลับมุมขวาล่าง ----------
        back_btn = ctk.CTkButton(
            self,
            text="ย้อนกลับ",
            fg_color="#c41216",
            hover_color="#800000",
            text_color="white",
            corner_radius=10,
            height=32,
            width=110,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=lambda: self.app.show_page("login"),
        )
        back_btn.place(relx=1.0, rely=1.0, x=-20, y=-20, anchor="se")

        # ---------- ข้อความสถานะเพิ่มตะกร้า ----------
        self.msg_label = ctk.CTkLabel(
            self,
            text="",
            text_color="green",
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="transparent",
        )
        self.msg_label.place(x=40, rely=1.0, y=-40, anchor="sw")

        # ค่าตั้งต้นและโหลดสินค้า
        self._current_category = "All"
        self.refresh_items()

    # -------------------------------------------------
    # Utilities
    # -------------------------------------------------
    def _apply_fullscreen_background(self, screen_w: int, screen_h: int, filename: str = "menu.png") -> None:
        """โหลดภาพเต็มจอจาก assets/<filename>; ถ้าไม่ได้ → สีเหลือง fallback"""
        from pathlib import Path
        base_dir = Path(__file__).parent.resolve()
        bg_path = base_dir / "assets" / filename
        try:
            pil_bg = Image.open(bg_path).resize((screen_w, screen_h), Image.LANCZOS)
            self.bg_img_ref = ctk.CTkImage(light_image=pil_bg, dark_image=pil_bg, size=(screen_w, screen_h))
            ctk.CTkLabel(self, image=self.bg_img_ref, text="").place(relx=0, rely=0, relwidth=1, relheight=1)
        except (FileNotFoundError, OSError):
            self.configure(fg_color="#f7dc5a")

    # -------------------------------------------------
    # สลับหมวดหมู่ -> รีเฟรชรายการ
    def _switch_category(self, cat_name: str):
        self._current_category = cat_name
        self.refresh_items()

    # -------------------------------------------------
    def refresh_items(self):
        # อัปเดต header ผู้ใช้ก่อน
        self.profile_header.refresh()

        # ล้างและโหลดสินค้าใหม่
        for w in self.items_scroll.winfo_children():
            w.destroy()

        selected_cat_ui = self._current_category  # "All","Combo","Set","Beverage"
        selected_cat_db = selected_cat_ui.lower()
        if selected_cat_db == "set":
            selected_cat_db = "size s"  # map UI -> DB เดิม

        with db_connect() as con:
            cur = con.cursor()
            if selected_cat_db == "all":
                cur.execute(
                    """
                    SELECT id, name, price, image_path, description, category
                    FROM products
                    ORDER BY id
                    """
                )
            else:
                cur.execute(
                    """
                    SELECT id, name, price, image_path, description, category
                    FROM products
                    WHERE lower(category)=?
                    ORDER BY id
                    """,
                    (selected_cat_db,),
                )
            rows = cur.fetchall()

        if not rows:
            ctk.CTkLabel(
                self.items_scroll,
                text="(ยังไม่มีสินค้าในหมวดนี้)",
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color="black",
                anchor="w",
            ).pack(fill="x", padx=10, pady=10)
            return

        for (pid, name, price, img_path, desc, _cat) in rows:
            qty_var = ctk.StringVar(value="1")

            card = ctk.CTkFrame(self.items_scroll, fg_color="#ffffff", corner_radius=8)
            card.pack(fill="x", padx=8, pady=(0, 12))

            # ซ้าย: พื้นที่รูป
            img_frame = ctk.CTkFrame(card, fg_color="#f4c20c", corner_radius=8, width=110, height=100)
            img_frame.grid(row=0, column=0, rowspan=2, padx=12, pady=12, sticky="n")
            img_frame.grid_propagate(False)

            try:
                if img_path and Path(img_path).exists():
                    pil_prod = Image.open(img_path).resize((100, 90), Image.LANCZOS)
                    small_ref = ctk.CTkImage(light_image=pil_prod, dark_image=pil_prod, size=(100, 90))
                    img_label = ctk.CTkLabel(img_frame, image=small_ref, text="")
                    img_label.image_ref_keep = small_ref  # กัน GC
                    img_label.pack(expand=True)
                else:
                    ctk.CTkLabel(img_frame, text="ไม่มีรูป").pack(expand=True)
            except (FileNotFoundError, OSError, ValueError):
                ctk.CTkLabel(img_frame, text="โหลดรูปไม่ได้").pack(expand=True)

            # ขวาบน: ชื่อ / ราคา / คำอธิบาย
            info_frame = ctk.CTkFrame(card, fg_color="transparent")
            info_frame.grid(row=0, column=1, sticky="nw", padx=(0, 12), pady=(12, 4))

            ctk.CTkLabel(
                info_frame,
                text=name,
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="black",
                anchor="w",
                justify="left",
            ).grid(row=0, column=0, sticky="w")

            ctk.CTkLabel(
                info_frame,
                text=f"{price:.0f} บาท",
                font=ctk.CTkFont(size=13),
                text_color="black",
                anchor="w",
                justify="left",
            ).grid(row=1, column=0, sticky="w", pady=(2, 4))

            shown_desc = desc.strip() if (desc and desc.strip()) else "รายละเอียดสินค้า"
            ctk.CTkLabel(
                info_frame,
                text=shown_desc,
                font=ctk.CTkFont(size=12),
                text_color="black",
                anchor="w",
                justify="left",
                wraplength=500,
            ).grid(row=2, column=0, sticky="w")

            # ขวาล่าง: จำนวน + ปุ่มใส่ตะกร้า
            action_frame = ctk.CTkFrame(card, fg_color="transparent")
            action_frame.grid(row=1, column=1, sticky="w", padx=(0, 12), pady=(4, 12))

            qty_area = ctk.CTkFrame(action_frame, fg_color="transparent")
            qty_area.pack(side="left")

            def dec_qty(v=qty_var):
                try:
                    q = int(v.get())
                    if q > 1:
                        v.set(str(q - 1))
                except ValueError:
                    v.set("1")

            def inc_qty(v=qty_var):
                try:
                    q = int(v.get())
                    v.set(str(q + 1))
                except ValueError:
                    v.set("1")

            ctk.CTkLabel(qty_area, text="จำนวน:", text_color="black", font=ctk.CTkFont(size=13)).pack(
                side="left", padx=(0, 6)
            )

            ctk.CTkButton(
                qty_area, text="-", width=28, height=28, corner_radius=6,
                fg_color="#000000", hover_color="#333333", text_color="white",
                font=ctk.CTkFont(size=14, weight="bold"), command=dec_qty
            ).pack(side="left")

            qty_entry = ctk.CTkEntry(qty_area, width=40, textvariable=qty_var, justify="center")
            qty_entry.pack(side="left")

            ctk.CTkButton(
                qty_area, text="+", width=28, height=28, corner_radius=6,
                fg_color="#000000", hover_color="#333333", text_color="white",
                font=ctk.CTkFont(size=14, weight="bold"), command=inc_qty
            ).pack(side="left", padx=(0, 6))

            def add_this_item(p_id=pid, p_name=name, p_price=price, v=qty_var):
                try:
                    q = int(v.get())
                    if q <= 0:
                        q = 1
                except ValueError:
                    q = 1
                self.app.add_to_cart(p_id, p_name, p_price, q)

            ctk.CTkButton(
                action_frame,
                text="ใส่ตะกร้า",
                height=32,
                corner_radius=8,
                fg_color="#bcab2e",
                hover_color="#cf7f17",
                text_color="black",
                font=ctk.CTkFont(size=14, weight="bold"),
                command=add_this_item,
            ).pack(side="left", padx=(12, 0))



class BasketPage(ctk.CTkFrame):
    """
    หน้า 'ตะกร้า':
    - แสดงรายการใน self.app.cart
    - ปรับจำนวน / ลบสินค้า
    - ราคารวม + ปุ่มย้อนกลับ/ชำระเงิน
    """

    def __init__(self, master, app):
        super().__init__(master)
        self.app = app

        # --- ขนาดจอครั้งเดียว ---
        screen_w = getattr(self.app, "WIDTH", 1280)
        screen_h = getattr(self.app, "HEIGHT", 720)

        # --- พื้นหลังเต็มจอ ---
        self._apply_fullscreen_background(screen_w, screen_h, filename="basket.png")

        # ====== โซนตาราง (ใหญ่ขึ้น) ======
        self.table_area = ctk.CTkFrame(self, fg_color="#fff9e4")
        self.table_area.place(relx=0.5, rely=0.58, anchor="center")
        self.table_area.grid_rowconfigure(0, weight=1)
        self.table_area.grid_columnconfigure(0, weight=1)

        # list_container = หัว + รายการ
        list_container = ctk.CTkFrame(self.table_area, fg_color="transparent")
        list_container.grid(row=0, column=0, sticky="nsew", padx=32, pady=(28, 16))
        list_container.grid_rowconfigure(1, weight=1)
        list_container.grid_columnconfigure(0, weight=1)

        # ค่าร่วมคอลัมน์
        PADX = 33
        self.COL_WEIGHTS = [5, 3, 3, 2, 3]
        self.COL_MINSIZE = [200, 140, 130, 80, 50]

        # ====== HEADER ======
        header_row = ctk.CTkFrame(list_container, fg_color="transparent")
        header_row.grid(row=0, column=0, sticky="ew", padx=PADX, pady=(0, 8))
        for i, (w, m) in enumerate(zip(self.COL_WEIGHTS, self.COL_MINSIZE)):
            header_row.grid_columnconfigure(i, weight=w, uniform="cart", minsize=m)

        ctk.CTkLabel(header_row, text="รายการ",
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color="black", anchor="w").grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(header_row, text="จำนวน",
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color="black", anchor="w").grid(row=0, column=1, sticky="w")

        ctk.CTkLabel(header_row, text="ราคา\n(ต่อหน่วย)",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="black", anchor="e").grid(row=0, column=2, sticky="e")

        ctk.CTkLabel(header_row, text="รวม",
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color="black", anchor="e").grid(row=0, column=3, sticky="e")

        ctk.CTkLabel(header_row, text="", font=ctk.CTkFont(size=22, weight="bold"),
                     text_color="black").grid(row=0, column=4, sticky="e")

        # ====== รายการ (Scrollable) ======
        self.items_frame = ctk.CTkScrollableFrame(list_container, fg_color="transparent", height=360)
        self.items_frame.grid(row=1, column=0, sticky="nsew", padx=PADX, pady=(0, 8))
        for i, (w, m) in enumerate(zip(self.COL_WEIGHTS, self.COL_MINSIZE)):
            self.items_frame.grid_columnconfigure(i, weight=w, uniform="cart", minsize=m)

        # ====== รวมด้านล่าง ======
        bottom_area = ctk.CTkFrame(self.table_area, fg_color="transparent")
        bottom_area.grid(row=1, column=0, sticky="ew", padx=32, pady=(0, 20))
        bottom_area.grid_columnconfigure(0, weight=1)
        bottom_area.grid_columnconfigure(1, weight=0)

        self.summary_left = ctk.CTkLabel(
            bottom_area, text="รวม",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color="black", anchor="w"
        )
        self.summary_left.grid(row=0, column=0, sticky="w")

        self.summary_right = ctk.CTkLabel(
            bottom_area, text="0 บาท",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color="black", anchor="e"
        )
        self.summary_right.grid(row=0, column=1, sticky="e")

        # ====== แถบปุ่มล่างเต็มกว้าง ======
        bar_bottom = ctk.CTkFrame(self, fg_color="#ffde59", corner_radius=0, height=72)
        bar_bottom.place(relx=0, rely=1.0, anchor="sw", relwidth=1.0)
        bar_bottom.grid_propagate(False)
        bar_bottom.grid_columnconfigure(0, weight=1)
        bar_bottom.grid_columnconfigure(1, weight=0)
        bar_bottom.grid_columnconfigure(2, weight=0)

        # ปุ่ม 'ย้อนกลับ' และ 'ชำระเงิน' ให้อยู่ขวาใน bar_bottom
        btn_right = ctk.CTkFrame(bar_bottom, fg_color="transparent")
        btn_right.grid(row=0, column=2, padx=20, pady=18, sticky="e")

        ctk.CTkButton(
            btn_right, text="ย้อนกลับ",
            fg_color="#d60c0c", hover_color="#800000", text_color="white",
            corner_radius=0, height=36, width=120,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=lambda: self.app.show_page("customermenu")
        ).grid(row=0, column=0, padx=(0, 10))

        ctk.CTkButton(
            btn_right, text="ชำระเงิน",
            fg_color="#1daa81", hover_color="#0a5839", text_color="white",
            corner_radius=0, height=36, width=120,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=lambda: self.app.show_page("payment")
        ).grid(row=0, column=1)

        # ---------- ข้อความสถานะเพิ่มตะกร้า (มุมซ้ายล่าง) ----------
        self.msg_label = ctk.CTkLabel(
            self, text="", text_color="green",
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="transparent"
        )
        self.msg_label.place(x=40, rely=1.0, y=-40, anchor="sw")

    # -----------------------------
    # Utilities
    # -----------------------------
    def _apply_fullscreen_background(self, screen_w: int, screen_h: int, filename: str = "basket.png") -> None:
        """โหลดภาพเต็มจอจาก assets/<filename>; ถ้าโหลดไม่ได้ → สีเหลือง fallback"""
        from pathlib import Path
        base_dir = Path(__file__).parent.resolve()
        bg_path = base_dir / "assets" / filename
        try:
            pil_bg = Image.open(bg_path).resize((screen_w, screen_h), Image.LANCZOS)
            self.bg_img_ref = ctk.CTkImage(light_image=pil_bg, dark_image=pil_bg, size=(screen_w, screen_h))
            ctk.CTkLabel(self, image=self.bg_img_ref, text="").place(relx=0, rely=0, relwidth=1, relheight=1)
        except (FileNotFoundError, OSError):
            self.configure(fg_color="#f7dc5a")

    # -----------------------------
    # แถวสินค้า
    # -----------------------------
    def _add_item_row(self, row_index, pid, name, qty, unit_price):
        line_total = qty * unit_price

        # คอลัมน์ 0: ชื่อสินค้า
        ctk.CTkLabel(
            self.items_frame, text=str(name),
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="black", anchor="w", justify="left"
        ).grid(row=row_index, column=0, sticky="w", pady=(2, 10))

        # คอลัมน์ 1: ปุ่ม - qty +
        qty_frame = ctk.CTkFrame(self.items_frame, fg_color="transparent")
        qty_frame.grid(row=row_index, column=1, sticky="w", pady=(2, 10))

        def dec_qty():
            current_q = int(self.app.cart[pid]["qty"])
            self.app.cart[pid]["qty"] = max(1, current_q - 1)
            self.refresh()

        def inc_qty():
            current_q = int(self.app.cart[pid]["qty"])
            self.app.cart[pid]["qty"] = current_q + 1
            self.refresh()

        ctk.CTkButton(
            qty_frame, text="-", width=34, height=34,
            corner_radius=8, fg_color="#000000", hover_color="#333333",
            text_color="white", font=ctk.CTkFont(size=16, weight="bold"),
            command=dec_qty
        ).pack(side="left")

        ctk.CTkLabel(
            qty_frame, text=str(qty),
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="black", width=40
        ).pack(side="left", padx=6)

        ctk.CTkButton(
            qty_frame, text="+", width=34, height=34,
            corner_radius=8, fg_color="#000000", hover_color="#333333",
            text_color="white", font=ctk.CTkFont(size=16, weight="bold"),
            command=inc_qty
        ).pack(side="left")

        # คอลัมน์ 2: ราคา/หน่วย
        ctk.CTkLabel(
            self.items_frame, text=f"{unit_price:,.0f}",
            font=ctk.CTkFont(size=18), text_color="black"
        ).grid(row=row_index, column=2, sticky="e", pady=(2, 10))

        # คอลัมน์ 3: รวม
        ctk.CTkLabel(
            self.items_frame, text=f"{line_total:,.0f}",
            font=ctk.CTkFont(size=18), text_color="black"
        ).grid(row=row_index, column=3, sticky="e", pady=(2, 10))

        # คอลัมน์ 4: ปุ่มลบ
        def remove_item():
            if pid in self.app.cart:
                del self.app.cart[pid]
            self.refresh()

        ctk.CTkButton(
            self.items_frame, text="ลบ",
            width=64, height=32, corner_radius=8,
            fg_color="#c41216", hover_color="#800000",
            text_color="white", font=ctk.CTkFont(size=16, weight="bold"),
            command=remove_item
        ).grid(row=row_index, column=4, sticky="e", pady=(2, 10), padx=(10, 0))

    # -----------------------------
    # refresh() เรียกทุกครั้งก่อนโชว์หน้า
    # -----------------------------
    def refresh(self):
        # ล้างรายการเก่า
        for w in self.items_frame.winfo_children():
            w.destroy()

        cart = self.app.cart
        if not cart:
            ctk.CTkLabel(
                self.items_frame,
                text="(ยังไม่มีสินค้าในตะกร้า)",
                font=ctk.CTkFont(size=16),
                text_color="black",
                anchor="w",
                justify="left",
            ).grid(row=0, column=0, sticky="w", pady=(0, 6))
            self.summary_left.configure(text="รวม")
            self.summary_right.configure(text="0 บาท")
            return

        total_all = 0.0
        r = 0
        for pid, item in cart.items():
            name = item["name"]
            qty = int(item["qty"])
            price = float(item["price"])
            total_all += qty * price

            self._add_item_row(r, pid, name, qty, price)
            r += 1

        self.summary_left.configure(text="รวม")
        self.summary_right.configure(text=f"{total_all:,.0f} บาท")



class PaymentPage(ctk.CTkFrame):
    """
    หน้าชำระเงิน:
    - ซ้าย: รายการสินค้าแบบใบเสร็จ + รวม
    - ขวา: การ์ด THAI QR + ปุ่มอัปโหลดสลิป
    - ล่าง: ปุ่ม 'ย้อนกลับ' และ 'ชำระเงิน'
    """
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.receipt_path = None  # เก็บไฟล์สลิปที่ผู้ใช้เลือก

        # ---------- BG ----------
        screen_w = getattr(self.app, "WIDTH", 1280)
        screen_h = getattr(self.app, "HEIGHT", 720)
        self._apply_fullscreen_background(screen_w, screen_h, filename="basket.png")

        # =============== ซ้าย: ใบรายการ ===============
        left_card = ctk.CTkFrame(self, fg_color="#fff5de", corner_radius=0, width=760, height=460)
        left_card.place(relx=0.36, rely=0.55, anchor="center")
        left_card.grid_propagate(False)
        left_card.grid_rowconfigure(0, weight=0)  # หัวตาราง
        left_card.grid_rowconfigure(1, weight=1)  # โซนรายการเลื่อน
        left_card.grid_rowconfigure(2, weight=0)  # แถวสรุปรวม

        # หัวตาราง
        header = ctk.CTkFrame(left_card, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(24, 8))
        for i, w in enumerate([3, 1, 1, 1]):
            header.grid_columnconfigure(i, weight=w)

        def H(txt, col):
            ctk.CTkLabel(
                header, text=txt, text_color="black",
                font=ctk.CTkFont(size=22, weight="bold")
            ).grid(row=0, column=col, sticky="w")

        H("รายการ", 0); H("จำนวน", 1); H("ราคา\n(ต่อหน่วย)", 2); H("รวม", 3)

        # เนื้อหารายการ (Scrollable)
        self.items_area = ctk.CTkScrollableFrame(left_card, fg_color="transparent", height=310, width=700)
        self.items_area.grid(row=1, column=0, sticky="nsew", padx=28, pady=(4, 0))
        for i, w in enumerate([3, 1, 1, 1]):
            self.items_area.grid_columnconfigure(i, weight=w)

        # แถวรวมด้านล่าง
        bottom = ctk.CTkFrame(left_card, fg_color="transparent")
        bottom.grid(row=2, column=0, sticky="ew", padx=28, pady=(8, 22))
        bottom.grid_columnconfigure(0, weight=1)
        bottom.grid_columnconfigure(1, weight=0)

        ctk.CTkLabel(
            bottom, text="รวม", text_color="black",
            font=ctk.CTkFont(size=26, weight="bold")
        ).grid(row=0, column=0, sticky="w")

        self.total_label = ctk.CTkLabel(
            bottom, text="0 บาท", text_color="black",
            font=ctk.CTkFont(size=26, weight="bold")
        )
        self.total_label.grid(row=0, column=1, sticky="e")

        # =============== ขวา: การ์ด QR + อัปโหลดสลิป ===============
        right_card = ctk.CTkFrame(self, fg_color="white", corner_radius=0, width=400, height=520)
        right_card.place(relx=0.79, rely=0.52, anchor="center")
        right_card.grid_propagate(False)

        # --- QR loader robust ---
        from pathlib import Path
        base_dir = Path(__file__).parent.resolve()
        qr_candidates = [base_dir / "assets" / "qr1.png"]  # เพิ่มชื่ออื่นได้ตามต้องการ
        qr_path = next((p for p in qr_candidates if p.exists()), None)

        if qr_path:
            try:
                pil_qr = Image.open(qr_path).convert("RGB").resize((280, 280), Image.LANCZOS)
            except (FileNotFoundError, OSError, ValueError):
                pil_qr = Image.new("RGB", (280, 280), "#ececec")
        else:
            pil_qr = Image.new("RGB", (280, 280), "#ececec")

        self.qr_ref = ctk.CTkImage(light_image=pil_qr, dark_image=pil_qr, size=(280, 280))
        ctk.CTkLabel(right_card, image=self.qr_ref, text="").pack(pady=(0, 8))

        if not qr_path:
            ctk.CTkLabel(
                right_card, text="ไม่พบไฟล์ภาพ QR Code",
                text_color="#b71c1c", font=ctk.CTkFont(size=12)
            ).pack(pady=(0, 6))

        # ปุ่มอัปโหลดสลิป
        self.btn_upload = ctk.CTkButton(
            right_card, text="  กรุณาแนบสลิป", width=320, height=44,
            fg_color="#ffcf3e", hover_color="#e4b62b", text_color="black",
            corner_radius=0, font=ctk.CTkFont(size=16, weight="bold"),
            command=self._choose_receipt
        )
        self.btn_upload.pack(pady=(6, 14))

        self.receipt_hint = ctk.CTkLabel(right_card, text="", text_color="#0a5839", font=ctk.CTkFont(size=12))
        self.receipt_hint.pack()

        # =============== แถบปุ่มล่าง ===============
        bar = ctk.CTkFrame(self, fg_color="#e9d052", corner_radius=0, height=68)
        bar.place(relx=0, rely=1, anchor="sw", relwidth=1.0)
        bar.grid_propagate(False)
        bar.grid_columnconfigure(0, weight=1)
        bar.grid_columnconfigure(1, weight=0)
        bar.grid_columnconfigure(2, weight=0)

        back_btn = ctk.CTkButton(
            bar, text="ย้อนกลับ", width=140, height=42,
            fg_color="#c41216", hover_color="#800000", text_color="white",
            corner_radius=12, font=ctk.CTkFont(size=16, weight="bold"),
            command=lambda: self.app.show_page("basket")
        )
        pay_btn = ctk.CTkButton(
            bar, text="ชำระเงิน", width=160, height=42,
            fg_color="#108a5a", hover_color="#0a5839", text_color="white",
            corner_radius=12, font=ctk.CTkFont(size=16, weight="bold"),
            command=self._confirm_payment
        )
        back_btn.grid(row=0, column=1, padx=(0, 10), pady=12, sticky="e")
        pay_btn.grid(row=0, column=2, padx=(0, 20), pady=12, sticky="e")

    # ---------- helpers ----------
    def refresh(self):
        """ถูกเรียกทุกครั้งที่สลับมาหน้านี้"""
        self._render_items()

    def _render_items(self):
        # ล้างก่อน
        for w in self.items_area.winfo_children():
            w.destroy()

        total = 0.0
        r = 0
        for pid, it in (self.app.cart or {}).items():
            name = str(it["name"])
            qty = int(it["qty"])
            price = float(it["price"])
            line = qty * price
            total += line

            ctk.CTkLabel(self.items_area, text=name, text_color="black",
                         font=ctk.CTkFont(size=20)).grid(row=r, column=0, sticky="w", pady=4)
            ctk.CTkLabel(self.items_area, text=str(qty), text_color="black",
                         font=ctk.CTkFont(size=20)).grid(row=r, column=1, sticky="w")
            ctk.CTkLabel(self.items_area, text=f"{price:,.0f}", text_color="black",
                         font=ctk.CTkFont(size=20)).grid(row=r, column=2, sticky="w")
            ctk.CTkLabel(self.items_area, text=f"{line:,.0f}", text_color="black",
                         font=ctk.CTkFont(size=20)).grid(row=r, column=3, sticky="w")
            r += 1

        self.total_label.configure(text=f"{total:,.0f} บาท")

    def _choose_receipt(self):
        path = filedialog.askopenfilename(
            title="เลือกไฟล์สลิปโอนเงิน",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.gif *.bmp"), ("PDF", "*.pdf")]
        )
        if not path:
            return
        self.receipt_path = path
        self.receipt_hint.configure(text="แนบสลิปเรียบร้อย ✅")

    def _confirm_payment(self):
        # 1) ต้องมีสินค้า
        if not self.app.cart:
            messagebox.showwarning("ตะกร้าว่าง", "ยังไม่มีสินค้าในตะกร้า")
            return

        # 2) บังคับแนบสลิป
        if not self.receipt_path:
            messagebox.showwarning("ต้องแนบสลิป", "กรุณาแนบสลิปก่อนกดชำระเงิน")
            return

        # 3) คำนวณรวม
        try:
            total = sum(int(v["qty"]) * float(v["price"]) for v in self.app.cart.values())
        except (ValueError, TypeError):
            total = 0.0

        paid_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        queue_code = generate_daily_queue()
        customer_name = self.app.current_user.get("full_name") if self.app.current_user else "-"

        # --- สร้าง order + บันทึก items ---
        try:
            with db_connect() as con:
                cur = con.cursor()

                # ตรวจว่ามี customer_id ไหม (รองรับ DB เก่า)
                cur.execute("PRAGMA table_info(orders)")
                ord_cols = [r[1] for r in cur.fetchall()]
                has_customer = "customer_id" in ord_cols

                # เริ่มธุรกรรม
                cur.execute("BEGIN;")

                # insert order
                if has_customer:
                    cur.execute(
                        """
                        INSERT INTO orders(queue_code, customer_name, total_price, paid_at, customer_id)
                        VALUES (?,?,?,?,?)
                        """,
                        (queue_code, customer_name, float(total), paid_at, (self.app.current_user or {}).get("id"))
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO orders(queue_code, customer_name, total_price, paid_at)
                        VALUES (?,?,?,?)
                        """,
                        (queue_code, customer_name, float(total), paid_at)
                    )

                order_id = cur.lastrowid

                # insert order_items + เช็คสต๊อกก่อนหัก
                for pid, v in self.app.cart.items():
                    qty = int(v.get("qty", 0) or 0)
                    price = float(v.get("price", 0) or 0)
                    line = float(qty * price)

                    cur.execute("SELECT stock FROM products WHERE id=?", (int(pid),))
                    row = cur.fetchone()
                    stock_now = int(row[0]) if row and row[0] is not None else 0
                    if qty <= 0 or stock_now < qty:
                        raise ValueError(f"สต๊อกไม่พอสำหรับสินค้า id={pid} (คงเหลือ {stock_now}, ต้องการ {qty})")

                    cur.execute(
                        """
                        INSERT INTO order_items(order_id, product_id, qty, unit_price, line_total)
                        VALUES (?,?,?,?,?)
                        """,
                        (order_id, int(pid), qty, price, line)
                    )

                    cur.execute("UPDATE products SET stock = stock - ? WHERE id = ?", (qty, int(pid)))

                # --------- จัดเก็บไฟล์สลิป ----------
                from pathlib import Path
                import shutil

                slip_path_db = None
                if self.receipt_path and Path(self.receipt_path).exists():
                    slip_dir = Path(RECEIPTS_DIR) / "slips"
                    slip_dir.mkdir(parents=True, exist_ok=True)
                    ext = Path(self.receipt_path).suffix.lower() or ".png"
                    dst = slip_dir / f"slip_{order_id}{ext}"
                    try:
                        shutil.copy(self.receipt_path, dst)
                        slip_path_db = str(dst)
                    except (OSError, shutil.Error) as e:
                        print("WARN: copy slip failed:", e)

                # ให้แน่ใจว่ามีคอลัมน์ slip_path (รองรับฐานข้อมูลเก่า)
                cur.execute("PRAGMA table_info(orders)")
                cols = [r[1] for r in cur.fetchall()]
                if "slip_path" not in cols:
                    try:
                        cur.execute("ALTER TABLE orders ADD COLUMN slip_path TEXT")
                    except sqlite3.DatabaseError:
                        pass

                if slip_path_db:
                    cur.execute("UPDATE orders SET slip_path=? WHERE id=?", (slip_path_db, order_id))

                # commit ธุรกรรมเมื่อทุกอย่างสำเร็จ
                con.commit()

        except sqlite3.DatabaseError as e:
            try:
                con.rollback()
            except Exception:
                pass
            messagebox.showerror("ทำรายการไม่สำเร็จ", f"เกิดข้อผิดพลาดจากฐานข้อมูล:\n{e}")
            return
        except Exception as e:
            messagebox.showerror("สร้างออเดอร์ไม่สำเร็จ", f"เกิดข้อผิดพลาด: {e}")
            return

        # --- เก็บ session ให้ ReceiptPage ใช้ ---
        self.app.receipt_info = {
            "order_id": order_id,
            "queue_code": queue_code,
            "items": [
                {
                    "name": str(it["name"]),
                    "qty": int(it["qty"]),
                    "price": float(it["price"]),
                    "line": int(it["qty"]) * float(it["price"]),
                }
                for it in self.app.cart.values()
            ],
            "total": float(total),
            "paid_at": paid_at,
            "customer_name": customer_name,
            "slip_path": slip_path_db,
        }

        # เคลียร์ตะกร้า → ไปหน้าใบเสร็จ
        self.app.cart = {}
        self.app.show_page("receipt")


    # ---------- BG helper ----------
    def _apply_fullscreen_background(self, screen_w: int, screen_h: int, filename: str = "basket.png") -> None:
        """โหลดภาพเต็มจอจาก assets/<filename>; ถ้าโหลดไม่ได้ → สีเหลือง fallback"""
        from pathlib import Path
        base_dir = Path(__file__).parent.resolve()
        bg_path = base_dir / "assets" / filename
        try:
            pil_bg = Image.open(bg_path).resize((screen_w, screen_h), Image.LANCZOS)
            self.bg_img_ref = ctk.CTkImage(light_image=pil_bg, dark_image=pil_bg, size=(screen_w, screen_h))
            ctk.CTkLabel(self, image=self.bg_img_ref, text="").place(relx=0, rely=0, relwidth=1, relheight=1)
        except (FileNotFoundError, OSError, ValueError):
            self.configure(fg_color="#f7dc5a")



class ReceiptPage(ctk.CTkFrame):
    """
    หน้าบิล / ใบเสร็จหลังจ่ายเงิน:
    - BG เหลืองลายไก่
    - กล่องบิลสีขาว
    - แสดงคิว, ชื่อร้าน, ลูกค้า, เวลา
    - ตารางรายการสินค้า
    - รวมทั้งหมด + ปุ่มดาวน์โหลด PDF
    - ปุ่ม 'ทำรายการต่อ' / 'ออกจากระบบ'
    """
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app

        # ---------- BG ----------
        screen_w = getattr(self.app, "WIDTH", 1280)
        screen_h = getattr(self.app, "HEIGHT", 720)
        self._apply_fullscreen_background(screen_w, screen_h, filename="receip.png")

        # ----- Header ผู้ใช้มุมซ้ายบน -----
        self.profile_header = ProfileHeader(self, self.app)
        self.profile_header.place(x=20, y=20, anchor="nw")

        # ---------- กล่องบิล ----------
        bill_card = ctk.CTkFrame(
            self, fg_color="#ffffff", corner_radius=10,
            width=700, height=screen_h - 140
        )
        bill_card.place(relx=0.5, rely=0.5, anchor="center")
        bill_card.grid_propagate(False)

        bill_card.grid_columnconfigure(0, weight=1)
        for r, wt in enumerate([0, 0, 0, 0, 1, 0, 0, 0, 0]):  # โครงร่าง
            bill_card.grid_rowconfigure(r, weight=wt)

        # --- คิวที่ (ชิดขวา) ---
        header_row = ctk.CTkFrame(bill_card, fg_color="transparent")
        header_row.grid(row=0, column=0, sticky="ew", pady=(15, 5), padx=20)
        header_row.grid_columnconfigure(0, weight=1)
        header_row.grid_columnconfigure(1, weight=0)

        self.queue_label = ctk.CTkLabel(
            header_row, text="คิว K000",
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color="black", anchor="e", justify="right"
        )
        self.queue_label.grid(row=0, column=1, sticky="e")

        # --- โลโก้ + ชื่อร้าน ---
        base_dir = Path(__file__).parent.resolve()
        logo_frame = ctk.CTkFrame(bill_card, fg_color="transparent")
        logo_frame.grid(row=1, column=0, sticky="n")

        self.logo_img_ref = None
        logo_path = base_dir / "assets" / "logo.png"
        if logo_path.exists():
            try:
                pil_logo = Image.open(logo_path)
                target_w = 80
                ratio = target_w / pil_logo.width
                target_h = int(pil_logo.height * ratio)
                pil_logo_resized = pil_logo.resize((target_w, target_h), Image.LANCZOS)
                self.logo_img_ref = ctk.CTkImage(
                    light_image=pil_logo_resized, dark_image=pil_logo_resized,
                    size=(target_w, target_h)
                )
                ctk.CTkLabel(logo_frame, image=self.logo_img_ref, text="").pack(pady=(0, 4))
            except (OSError, ValueError):
                ctk.CTkLabel(
                    logo_frame, text="(LOGO)",
                    font=ctk.CTkFont(size=16, weight="bold"), text_color="black"
                ).pack(pady=(0, 4))
        else:
            ctk.CTkLabel(
                logo_frame, text="(LOGO)",
                font=ctk.CTkFont(size=16, weight="bold"), text_color="black"
            ).pack(pady=(0, 4))

        ctk.CTkLabel(
            logo_frame, text="ร้านไก่ก้อบกรอบ",
            font=ctk.CTkFont(size=18, weight="bold"), text_color="black", justify="center"
        ).pack()

        ctk.CTkLabel(
            logo_frame,
            text="“กรอบอร่อยจนลืมแฟนเก่า\nกรอบกว่าเรื่องราวที่ผ่านมา” ",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="black", justify="center"
        ).pack()
        ctk.CTkLabel(
            logo_frame,
            text="Tax ID: 673050553-2",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="black", justify="center"
        ).pack()

        # --- ลูกค้า + เวลา ---
        self.customer_time_label = ctk.CTkLabel(
            bill_card,
            text="ชื่อลูกค้า: -\nวันที่: -\nเวลา: -",
            font=ctk.CTkFont(size=15), text_color="black",
            justify="left", anchor="w"
        )
        self.customer_time_label.grid(row=2, column=0, padx=20, pady=(10, 10), sticky="w")

        # --- หัวตารางสินค้า ---
        header_frame = ctk.CTkFrame(bill_card, fg_color="transparent")
        header_frame.grid(row=3, column=0, sticky="ew", padx=20)
        for i, w in enumerate([3, 1, 1, 1]):
            header_frame.grid_columnconfigure(i, weight=w)

        def col_head(txt, col):
            ctk.CTkLabel(
                header_frame, text=txt, text_color="black",
                font=ctk.CTkFont(size=15, weight="bold")
            ).grid(row=0, column=col, sticky="w")

        col_head("รายการ", 0)
        col_head("จำนวน", 1)
        col_head("ราคา/หน่วย", 2)
        col_head("รวม", 3)

        # --- โซนเลื่อนรายการสินค้า ---
        self.bill_scroll = ctk.CTkScrollableFrame(bill_card, fg_color="transparent")
        self.bill_scroll.grid(row=4, column=0, sticky="nsew", padx=20, pady=(0, 10))
        for i, w in enumerate([3, 1, 1, 1]):
            self.bill_scroll.grid_columnconfigure(i, weight=w)

        # --- สรุปรวมทั้งหมด ---
        self.subtotal_label = ctk.CTkLabel(
            bill_card, text="sub total: 0 บาท", text_color="black",
            font=ctk.CTkFont(size=14)
        )
        self.subtotal_label.grid(row=6, column=0, sticky="e", padx=20, pady=(0, 4))

        self.vat_label = ctk.CTkLabel(
            bill_card, text="vat 7%: 0 บาท", text_color="black",
            font=ctk.CTkFont(size=14)
        )
        self.vat_label.grid(row=7, column=0, sticky="e", padx=20, pady=(0, 4))

        self.net_label = ctk.CTkLabel(
            bill_card, text="total: 0 บาท", text_color="black",
            font=ctk.CTkFont(size=15, weight="bold")
        )
        self.net_label.grid(row=8, column=0, sticky="e", padx=20, pady=(0, 12))

        # ปุ่มดาวน์โหลด PDF
        self.btn_pdf = ctk.CTkButton(
            bill_card, text="ดาวน์โหลดบิล (PDF)",
            fg_color="#bcab2e", hover_color="#cf7f17",
            text_color="black", corner_radius=8, height=32,
            command=self._download_pdf
        )
        self.btn_pdf.grid(row=9, column=0, pady=(0, 12))

        # --- ปุ่มล่างขวา ---
        btn_container = ctk.CTkFrame(self, fg_color="transparent")
        btn_container.place(relx=1.0, rely=1.0, anchor="se", x=-20, y=-20)
        btn_container.grid_columnconfigure(0, weight=1)

        self.btn_continue = ctk.CTkButton(
            btn_container, text="ทำรายการต่อ",
            fg_color="#108a5a", hover_color="#0a5839",
            text_color="white", corner_radius=10,
            height=36, width=180, font=ctk.CTkFont(size=14, weight="bold"),
            command=lambda: self.app.show_page("customermenu")
        )
        self.btn_continue.grid(row=0, column=0, sticky="e", pady=(0, 8))

        self.btn_logout = ctk.CTkButton(
            btn_container, text="ออกจากระบบ",
            fg_color="#c41216", hover_color="#800000",
            text_color="white", corner_radius=10,
            height=36, width=180, font=ctk.CTkFont(size=14, weight="bold"),
            command=self._logout
        )
        self.btn_logout.grid(row=1, column=0, sticky="e")

    # ---------- session / render ----------
    def _logout(self):
        """ล้าง session แล้วกลับหน้า login"""
        self.app.current_user = None
        self.app.cart = {}
        self.app.receipt_info = {}
        self.app.show_page("login")

    def _add_line(self, row_index: int, name: str, qty: int, unit_price: float):
        """แสดง 1 แถวสินค้าในใบเสร็จ"""
        try:
            qty_val = int(qty)
        except (TypeError, ValueError):
            qty_val = 0
        try:
            unit_val = float(unit_price)
        except (TypeError, ValueError):
            unit_val = 0.0

        line_total = qty_val * unit_val

        ctk.CTkLabel(self.bill_scroll, text=name, text_color="black",
                     font=ctk.CTkFont(size=15)).grid(row=row_index, column=0, sticky="w", pady=2)
        ctk.CTkLabel(self.bill_scroll, text=str(qty_val), text_color="black",
                     font=ctk.CTkFont(size=15)).grid(row=row_index, column=1, sticky="w", pady=2)
        ctk.CTkLabel(self.bill_scroll, text=f"{unit_val:,.0f}", text_color="black",
                     font=ctk.CTkFont(size=15)).grid(row=row_index, column=2, sticky="w", pady=2)
        ctk.CTkLabel(self.bill_scroll, text=f"{line_total:,.0f}", text_color="black",
                     font=ctk.CTkFont(size=15)).grid(row=row_index, column=3, sticky="w", pady=2)

    def refresh(self):
        """เรียกก่อนโชว์หน้า: เติมข้อมูลบิลจาก self.app.receipt_info"""
        self.profile_header.refresh()

        for w in self.bill_scroll.winfo_children():
            w.destroy()

        info = getattr(self.app, "receipt_info", None)
        if not info:
            self._add_line(0, "(ไม่พบข้อมูลออเดอร์)", "-", 0)
            self.queue_label.configure(text="คิว K000")
            self.customer_time_label.configure(text="ชื่อลูกค้า: -\nวันที่: -\nเวลา: -")
            return

        queue_code = info.get("queue_code", "K000")
        paid_at    = info.get("paid_at", "-")
        items      = info.get("items", [])
        customer   = info.get("customer_name", "-")

        # จัดรูปแบบวันที่/เวลา
        try:
            dt_obj    = datetime.strptime(paid_at, "%Y-%m-%d %H:%M:%S")
            nice_date = dt_obj.strftime("%d/%m/%Y")
            nice_time = dt_obj.strftime("%H:%M")
        except (TypeError, ValueError):
            nice_date, nice_time = paid_at, ""

        self.queue_label.configure(text=f"คิว {queue_code}")
        self.customer_time_label.configure(
            text=f"ชื่อลูกค้า: {customer}\n\nวันที่: {nice_date}\nเวลา: {nice_time}"
        )

        subtotal = 0.0
        for idx, it in enumerate(items):
            name  = str(it.get("name", "-"))
            qty   = int(it.get("qty", 0) or 0)
            price = float(it.get("price", 0) or 0.0)
            subtotal += qty * price
            self._add_line(idx, name, qty, price)

        vat = round(subtotal * 0.07, 2)
        net = round(subtotal + vat, 2)

        self.subtotal_label.configure(text=f"sub total: {subtotal:,.0f} บาท")
        self.vat_label.configure(text=f"vat 7%: {vat:,.0f} บาท")
        self.net_label.configure(text=f"total: {net:,.0f} บาท")

    # ---------- export PDF ----------
    def _download_pdf(self):
        """บันทึกใบเสร็จเป็น PDF (ใช้ reportlab)"""
        if pdf_canvas is None:
            messagebox.showwarning("Library missing", "Please install 'reportlab' to export PDF.")
            return

        info = getattr(self.app, "receipt_info", None)
        if not info or not info.get("items"):
            messagebox.showwarning("No data", "There is no receipt data to print.")
            return

        order_id   = info.get("order_id", "-")
        queue_code = info.get("queue_code", "-")
        customer   = info.get("customer_name", "-")
        paid_at    = info.get("paid_at", "")
        items      = info.get("items", [])

        # โฟลเดอร์ปลายทาง
        try:
            os.makedirs(str(RECEIPTS_DIR), exist_ok=True)
        except OSError:
            pass

        default_name = f"receipt_{order_id}.pdf"
        try:
            pdf_path = filedialog.asksaveasfilename(
                title="Save receipt as PDF",
                defaultextension=".pdf",
                initialfile=default_name,
                filetypes=[("PDF", "*.pdf")],
                initialdir=str(RECEIPTS_DIR)
            )
        except Exception:
            pdf_path = ""
        if not pdf_path:
            pdf_path = os.path.join(str(RECEIPTS_DIR), default_name)

        # ฟอนต์ไทย (ถ้ามี) → ไม่มีก็ Helvetica
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        TH_FONT = "Helvetica"
        try:
            font_dir = Path(__file__).parent.resolve() / "assets" / "fonts"
            th_path  = font_dir / "THSarabunNew.ttf"
            thb_path = font_dir / "THSarabunNew-Bold.ttf"
            if th_path.exists():
                pdfmetrics.registerFont(TTFont("THSarabunNew", str(th_path)))
                TH_FONT = "THSarabunNew"
            if thb_path.exists():
                pdfmetrics.registerFont(TTFont("THSarabunNew-Bold", str(thb_path)))
        except Exception:
            TH_FONT = "Helvetica"

        # วาด PDF
        try:
            from reportlab.lib.pagesizes import A4
            c = pdf_canvas.Canvas(str(pdf_path), pagesize=A4)
            w, h = A4
            y = h - 60

            # Header: Queue
            c.setFont(TH_FONT, 24)
            c.drawRightString(w - 50, h - 40, f"Queue No: {queue_code}")

            # โลโก้กึ่งกลาง
            try:
                logo_path = Path(__file__).parent.resolve() / "assets" / "logo.png"
                if logo_path.exists():
                    c.drawImage(str(logo_path), w/2 - 40, y - 90, 80, 80, preserveAspectRatio=True, mask='auto')
            except Exception:
                pass

            # ชื่อร้าน + สโลแกน + Tax ID (อยู่ใต้สโลแกน)
            y -= 110
            c.setFont(TH_FONT, 18); c.drawCentredString(w/2, y, "KAIKOBKROB CHICKEN")
            y -= 18
            c.setFont(TH_FONT, 12); c.drawCentredString(w/2, y, "“Crispy that makes you forget your ex”")
            y -= 14;                c.drawCentredString(w/2, y, "“Crunchier than your past stories”")
            y -= 16;                c.drawCentredString(w/2, y, "Tax ID: 673050553-2")  # ← ย้ายมาอยู่ใต้สโลแกนตามต้องการ

            # แปลงวันที่/เวลา
            try:
                dt = datetime.strptime(paid_at, "%Y-%m-%d %H:%M:%S")
                nice_date = dt.strftime("%d/%m/%Y")
                nice_time = dt.strftime("%H:%M")
            except (TypeError, ValueError):
                nice_date, nice_time = paid_at, ""

            # บล็อกลูกค้า: จัดวาง "User / Date / Time" ลงมาคนละบรรทัด
            y -= 26; c.line(40, y, w - 40, y)
            y -= 16; c.setFont(TH_FONT, 12); c.drawString(50, y, f"User: {customer}")
            y -= 16; c.drawString(50, y, f"Date: {nice_date}")
            y -= 16; c.drawString(50, y, f"Time: {nice_time}")

            # หัวตาราง
            y -= 24; c.line(40, y, w - 40, y); y -= 16
            c.setFont(TH_FONT, 12)
            c.drawString(60, y, "Item")
            c.drawRightString(w - 220, y, "Qty")
            c.drawRightString(w - 140, y, "Price")
            c.drawRightString(w - 60,  y, "Total")
            y -= 8; c.line(40, y, w - 40, y)

            # แถวรายการ
            subtotal = 0.0
            c.setFont(TH_FONT, 12)
            for it in items:
                name  = str(it.get("name", "-"))
                qty   = int(it.get("qty", it.get("quantity", 0)) or 0)
                price = float(it.get("price", it.get("unit_price", 0)) or 0)
                line  = qty * price
                subtotal += line

                if y < 120:
                    c.showPage(); w, h = A4; y = h - 60
                    c.setFont(TH_FONT, 12)

                y -= 18
                c.drawString(60, y, name)
                c.drawRightString(w - 220, y, f"x{qty}")
                c.drawRightString(w - 140, y, f"{price:,.0f}")
                c.drawRightString(w - 60,  y, f"{line:,.0f}")

            # สรุปยอด
            vat   = round(subtotal * 0.07, 2)
            total = round(subtotal + vat, 2)
            y -= 12; c.line(40, y, w - 40, y); y -= 20
            c.setFont(TH_FONT, 12); c.drawRightString(w - 140, y, "Sub total:"); c.drawRightString(w - 60, y, f"{subtotal:,.0f}")
            y -= 16; c.drawRightString(w - 140, y, "VAT 7%:");    c.drawRightString(w - 60, y, f"{vat:,.0f}")
            y -= 16; c.setFont(TH_FONT, 13); c.drawRightString(w - 140, y, "Total:"); c.drawRightString(w - 60, y, f"{total:,.0f}")

            # Footer
            y -= 30; c.line(40, y, w - 40, y); y -= 18
            c.setFont(TH_FONT, 11); c.drawCentredString(w/2, y, "THANK YOU FOR YOUR PAYMENT")
            y -= 16; c.setFont(TH_FONT, 10); c.drawCentredString(w/2, y, "Wi-Fi : Kaikobkrob_5G     Password : 6666666666")

            c.showPage()
            c.save()
        except Exception as e:
            messagebox.showerror("Save failed", f"Could not save PDF:\n{e}")
            return

        # อัปเดต path ลง DB (optional)
        try:
            with db_connect() as con:
                cur = con.cursor()
                cur.execute("PRAGMA table_info(orders)")
                cols = [r[1] for r in cur.fetchall()]
                if "receipt_pdf_path" not in cols:
                    try:
                        cur.execute("ALTER TABLE orders ADD COLUMN receipt_pdf_path TEXT")
                    except sqlite3.DatabaseError:
                        pass
                if isinstance(order_id, int):
                    cur.execute("UPDATE orders SET receipt_pdf_path=? WHERE id=?", (str(pdf_path), order_id))
        except sqlite3.DatabaseError as e:
            print("WARN: DB update failed:", e)

        # เปิดไฟล์อัตโนมัติ (ถ้าทำได้)
        try:
            if os.name == "nt":
                os.startfile(str(pdf_path))
            elif sys.platform == "darwin":
                subprocess.call(["open", str(pdf_path)])
            else:
                subprocess.call(["xdg-open", str(pdf_path)])
        except Exception as e:
            print("WARN: auto-open pdf failed:", e)


    # ---------- helpers ----------
    def _apply_fullscreen_background(self, screen_w: int, screen_h: int, filename: str = "bg_login.png") -> None:
        """โหลดภาพเต็มจอจาก assets/<filename>; ถ้าโหลดไม่ได้ → สีเหลือง fallback"""
        bg_path = Path(__file__).parent.resolve() / "assets" / filename
        try:
            pil_bg = Image.open(bg_path).resize((screen_w, screen_h), Image.LANCZOS)
            self.bg_img_ref = ctk.CTkImage(light_image=pil_bg, dark_image=pil_bg, size=(screen_w, screen_h))
            ctk.CTkLabel(self, image=self.bg_img_ref, text="").place(relx=0, rely=0, relwidth=1, relheight=1)
        except (FileNotFoundError, OSError, ValueError):
            self.configure(fg_color="#f7dc5a")


#--------------------------------------------------------------------------------
# ระบบหลังบ้าน (Admin)
#--------------------------------------------------------------------------------
class AdminMenuPage(ctk.CTkFrame):
    """
    เมนูแอดมิน:
    - ปุ่มไป 'สต๊อกสินค้า'
    - ปุ่มไป 'ยอดขาย'
    - ปุ่ม 'ย้อนกลับ (ออกจากระบบ)'
    - พื้นหลังภาพเหลืองให้เข้าชุดกับหน้าอื่น
    """
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app

        # ---------- พื้นหลังเต็มจอ ----------
        screen_w = getattr(self.app, "WIDTH", 1280)
        screen_h = getattr(self.app, "HEIGHT", 720)

        base_dir = os.path.dirname(os.path.abspath(__file__))
        bg_path  = os.path.join(base_dir, "assets", "bg_0.png")
        try:
            pil_bg = Image.open(bg_path).resize((screen_w, screen_h), Image.LANCZOS)
            self.bg_img_ref = ctk.CTkImage(light_image=pil_bg, dark_image=pil_bg, size=(screen_w, screen_h))
            ctk.CTkLabel(self, image=self.bg_img_ref, text="").place(relx=0, rely=0, relwidth=1, relheight=1)
        except Exception:
            # ถ้ารูปหาย/เปิดไม่ได้ ให้ใช้พื้นเหลืองแทน
            self.configure(fg_color="#f7dc5a")

        # ---------- การ์ดเมนูกลาง ----------
        card_frame = ctk.CTkFrame(
            self, corner_radius=16, fg_color="#2b2b2b",
            width=360, height=260
        )
        card_frame.place(relx=0.5, rely=0.45, anchor="center")
        card_frame.grid_propagate(False)
        card_frame.grid_columnconfigure(0, weight=1)

        # หัวข้อ
        ctk.CTkLabel(
            card_frame, text="เมนูแอดมิน",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color="white"
        ).grid(row=0, column=0, pady=(20, 16), padx=20, sticky="n")

        # ปุ่มไป 'สต๊อกสินค้า'
        ctk.CTkButton(
            card_frame, text="สต๊อกสินค้า",
            height=40, corner_radius=10,
            fg_color="#1f6aa5", hover_color="#174d78",
            text_color="white", font=ctk.CTkFont(size=15, weight="bold"),
            command=lambda: self.app.show_page("stock")
        ).grid(row=1, column=0, padx=40, pady=(0, 12), sticky="ew")

        # ปุ่มไป 'ยอดขาย'
        ctk.CTkButton(
            card_frame, text="ยอดขาย",
            height=40, corner_radius=10,
            fg_color="#1f6aa5", hover_color="#174d78",
            text_color="white", font=ctk.CTkFont(size=15, weight="bold"),
            command=lambda: self.app.show_page("sales")
        ).grid(row=2, column=0, padx=40, pady=(0, 20), sticky="ew")

        # เส้นคั่นบาง ๆ
        ctk.CTkFrame(card_frame, fg_color="#444444", height=1).grid(
            row=3, column=0, padx=40, pady=(0, 16), sticky="ew"
        )

        # ปุ่มย้อนกลับ (ออกจากระบบ)
        ctk.CTkButton(
            card_frame, text="ย้อนกลับ (ออกจากระบบ)",
            height=36, corner_radius=10,
            fg_color="gray", hover_color="#555555",
            text_color="white", font=ctk.CTkFont(size=14, weight="bold"),
            command=self._logout
        ).grid(row=4, column=0, padx=40, pady=(0, 20), sticky="ew")

        # เครดิตมุมขวาล่าง (ใช้ fg_color โปร่งใสแทน bg_color)
        ctk.CTkLabel(
            self, text="Admin Panel",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#2b2b2b"
        ).place(relx=1.0, rely=1.0, x=-20, y=-20, anchor="se")

    def _logout(self):
        """ล้าง session แล้วกลับหน้า Login"""
        self.app.current_user = None
        self.app.cart = {}
        self.app.show_page("login")

        
class ProductManagePage(ctk.CTkFrame):
    """
    จัดการสินค้า (เพิ่ม / แก้ไข / ลบ)
    - ซ้าย: รายการสินค้า
    - ขวา: ฟอร์มแก้ไข + เลือกรูป
    """
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app

        screen_w = getattr(self.app, "WIDTH", 1280)
        screen_h = getattr(self.app, "HEIGHT", 720)

        # ---------- state ฟอร์ม ----------
        self.current_pid: int | None = None    # None = เพิ่มใหม่
        self.current_desc: str = ""            # เก็บ description เดิม (ตอนนี้ยังไม่เปิดให้แก้ผ่าน UI)
        self.original_image_path: str | None = None
        self.image_path: str | None = None     # path รูปใหม่ที่เพิ่งเลือก (ยังไม่ commit ลง DB)
        self.preview_img: ctk.CTkImage | None = None  # กัน GC

        self.base_dir = os.path.dirname(os.path.abspath(__file__))

        # ---------- BG ----------
        bg_image_path = os.path.join(self.base_dir, "assets", "bg_0.png")
        try:
            pil_bg = Image.open(bg_image_path).resize((screen_w, screen_h), Image.LANCZOS)
            self.bg_img_ref = ctk.CTkImage(light_image=pil_bg, dark_image=pil_bg, size=(screen_w, screen_h))
            ctk.CTkLabel(self, image=self.bg_img_ref, text="").place(relx=0, rely=0, relwidth=1, relheight=1)
        except Exception:
            self.configure(fg_color="#2b2b2b")  # fallback

        # ---------- dummy image (fallback เวลาไม่มีรูปสินค้า) ----------
        dummy = Image.new("RGB", (110, 110), color="black")
        ddraw = ImageDraw.Draw(dummy)
        ddraw.text((10, 40), "(ไม่มีรูป)", fill="white")
        self._dummy_pil = dummy
        self._dummy_ctk = ctk.CTkImage(light_image=dummy, dark_image=dummy, size=(110, 110))

        # ---------- กล่องหลัก ----------
        wrapper = ctk.CTkFrame(self, corner_radius=16, fg_color="#2b2b2b", width=800, height=500)
        wrapper.place(relx=0.5, rely=0.5, anchor="center")
        wrapper.grid_propagate(False)
        wrapper.grid_columnconfigure(0, weight=0)
        wrapper.grid_columnconfigure(1, weight=1)
        wrapper.grid_rowconfigure(0, weight=1)

        # ปุ่มย้อนกลับ (ไปหน้า admin)
        self.back_fab = ctk.CTkButton(
            self, text="ย้อนกลับ", fg_color="#c41216", hover_color="#800000",
            text_color="white", corner_radius=10, height=38, width=120,
            font=ctk.CTkFont(size=15, weight="bold"),
            command=lambda: self.app.show_page("adminmenu")
        )
        self.back_fab.place(relx=1.0, rely=1.0, x=-20, y=-20, anchor="se")

        # ============ ซ้าย: รายการสินค้า ============
        left_frame = ctk.CTkFrame(wrapper, corner_radius=12, fg_color="#1f1f1f", width=260)
        left_frame.grid(row=0, column=0, sticky="nsw", padx=(16, 8), pady=16)
        left_frame.grid_propagate(False)
        left_frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(left_frame, text="สินค้า",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="white").grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 6))

        self.product_list_frame = ctk.CTkScrollableFrame(left_frame, width=230, height=320, fg_color="transparent")
        self.product_list_frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

        self.btn_new = ctk.CTkButton(
            left_frame, text="เพิ่มสินค้าใหม่",
            fg_color="#bcab2e", hover_color="#cf7f17", text_color="black",
            corner_radius=10, font=ctk.CTkFont(size=14, weight="bold"),
            command=self._new_product_mode
        )
        self.btn_new.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))

        # ============ ขวา: ฟอร์มสินค้า ============
        right_frame = ctk.CTkScrollableFrame(wrapper, corner_radius=12, fg_color="#3a3a3a")
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(8, 16), pady=16)
        right_frame.grid_columnconfigure(0, weight=1)

        # ชื่อสินค้า
        ctk.CTkLabel(right_frame, text="ชื่อสินค้า",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="white").grid(row=0, column=0, sticky="w", padx=12, pady=(12, 3))
        self.ed_name = ctk.CTkEntry(right_frame, height=32, font=ctk.CTkFont(size=14))
        self.ed_name.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))

        # ราคา
        ctk.CTkLabel(right_frame, text="ราคา (บาท)",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="white").grid(row=2, column=0, sticky="w", padx=12, pady=(0, 3))
        self.ed_price = ctk.CTkEntry(right_frame, height=32, font=ctk.CTkFont(size=14))
        self.ed_price.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 8))

        # สต๊อก
        ctk.CTkLabel(right_frame, text="สต๊อกคงเหลือ",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="white").grid(row=4, column=0, sticky="w", padx=12, pady=(0, 3))
        self.ed_stock = ctk.CTkEntry(right_frame, height=32, font=ctk.CTkFont(size=14))
        self.ed_stock.grid(row=5, column=0, sticky="ew", padx=12, pady=(0, 8))

        # หมวดหมู่
        ctk.CTkLabel(right_frame, text="หมวดหมู่",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="white").grid(row=6, column=0, sticky="w", padx=12, pady=(0, 3))
        self.cat_var = ctk.StringVar(value="all")
        self.cat_menu = ctk.CTkOptionMenu(
            right_frame, variable=self.cat_var, values=["all", "combo", "size s", "beverage"], width=180
        )
        self.cat_menu.grid(row=7, column=0, sticky="w", padx=12, pady=(0, 12))

        # รูปสินค้า + preview
        ctk.CTkLabel(right_frame, text="รูปสินค้า",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="white").grid(row=8, column=0, sticky="w", padx=12, pady=(0, 3))

        self.preview_label = ctk.CTkLabel(right_frame, text="", width=110, height=110,
                                          fg_color="transparent", image=self._dummy_ctk)
        self.preview_label.grid(row=9, column=0, sticky="w", padx=12, pady=(0, 8))
        self.preview_label._img_ref = self._dummy_ctk
        self.preview_img = self._dummy_ctk  # ค่าเริ่มต้น

        # helper: ตั้งรูป preview จาก PIL image (หรือ dummy)
        def _set_preview_from_pil(pil_img: Image.Image | None):
            if pil_img is None:
                self.preview_img = self._dummy_ctk
            else:
                resized = pil_img.resize((110, 110), Image.LANCZOS)
                self.preview_img = ctk.CTkImage(light_image=resized, dark_image=resized, size=(110, 110))
            self.preview_label.configure(image=self.preview_img, text="")
            self.preview_label._img_ref = self.preview_img  # กัน GC
        self._set_preview_from_pil = _set_preview_from_pil

        # ปุ่มเลือกรูป (เซฟรูปใหม่ลง assets/products พร้อมชื่อไม่ชน)
        def _pick_image():
            p = filedialog.askopenfilename(
                title="เลือกรูปสินค้า",
                filetypes=[("Image files", "*.png *.jpg *.jpeg *.webp *.gif *.bmp")]
            )
            if not p:
                return
            try:
                # สร้างโฟลเดอร์ปลายทาง
                products_dir = os.path.join(self.base_dir, "assets", "products")
                os.makedirs(products_dir, exist_ok=True)

                # ตั้งชื่อใหม่กันชน: product_<timestamp>.<ext>
                ext = os.path.splitext(p)[1].lower() or ".png"
                new_name = f"product_{int(datetime.now().timestamp())}{ext}"
                dst_path = os.path.join(products_dir, new_name)

                # resize ให้พอดี (ไม่ใหญ่เกิน) แล้วบันทึก
                pil = Image.open(p).convert("RGB")
                pil.thumbnail((512, 512), Image.LANCZOS)   # จำกัดขนาดสูงสุด
                pil.save(dst_path)

                # อัปเดต state + preview
                self.image_path = dst_path
                self._set_preview_from_pil(pil)

                self.lbl_msg.configure(text="เลือกรูปสำเร็จ ✓ (ยังไม่บันทึกลงฐานข้อมูลจนกด 'บันทึกสินค้า')",
                                       text_color="#d1ffb0")
            except Exception as e:
                self.lbl_msg.configure(text=f"เลือกรูปไม่สำเร็จ: {e}", text_color="red")

        self.btn_pick_image = ctk.CTkButton(
            right_frame, text="เลือกรูปสินค้า...",
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#1f6aa5", hover_color="#174d78", text_color="white",
            command=_pick_image
        )
        self.btn_pick_image.grid(row=10, column=0, sticky="w", padx=12, pady=(0, 16))

        # สถานะ/ข้อความแจ้ง
        self.lbl_msg = ctk.CTkLabel(right_frame, text="", text_color="white", font=ctk.CTkFont(size=12))
        self.lbl_msg.grid(row=11, column=0, sticky="w", padx=12, pady=(0, 12))

        # ปุ่มล่าง
        btn_area = ctk.CTkFrame(right_frame, fg_color="transparent")
        btn_area.grid(row=12, column=0, sticky="ew", padx=12, pady=(8, 16))
        btn_area.grid_columnconfigure((0, 1, 2), weight=1)

        self.btn_save = ctk.CTkButton(
            btn_area, text="บันทึกสินค้า", height=40, corner_radius=10,
            fg_color="#bcab2e", hover_color="#cf7f17", text_color="black",
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self._save_product
        )
        self.btn_save.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.btn_delete = ctk.CTkButton(
            btn_area, text="ลบสินค้า", height=40, corner_radius=10,
            fg_color="#b71c1c", hover_color="#7f0000", text_color="white",
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self._delete_product
        )
        self.btn_delete.grid(row=0, column=1, sticky="ew", padx=6)

        # โหมดเริ่มต้น
        self._new_product_mode()
        self.refresh_product_list()

    # -----------------------------
    # ส่วน list สินค้า (ซ้าย)
    # -----------------------------
    def refresh_product_list(self):
        for w in self.product_list_frame.winfo_children():
            w.destroy()

        con = db_connect(); cur = con.cursor()
        cur.execute("SELECT id, name, price, stock FROM products ORDER BY id")
        rows = cur.fetchall()
        con.close()

        if not rows:
            ctk.CTkLabel(self.product_list_frame, text="(ยังไม่มีสินค้า)", text_color="white").pack(pady=10)
            return

        for (pid, name, price, stock) in rows:
            display_text = f"{name}\n{price:.0f} บาท | คงเหลือ {stock}"
            ctk.CTkButton(
                self.product_list_frame, text=display_text, height=60,
                command=lambda p=pid: self._load_product(p)
            ).pack(fill="x", padx=5, pady=5)

    # -----------------------------
    # โหมดเพิ่มสินค้าใหม่
    # -----------------------------
    def _clear_form(self):
        self.current_pid = None
        self.current_desc = ""
        self.original_image_path = None
        self.image_path = None

        self.ed_name.delete(0, "end")
        self.ed_price.delete(0, "end")
        self.ed_stock.delete(0, "end")
        self.cat_var.set("all")

        self._set_preview_from_pil(None)
        self.lbl_msg.configure(text="โหมดเพิ่มสินค้าใหม่", text_color="yellow")
        self.btn_delete.configure(state="disabled")

    def _new_product_mode(self):
        self._clear_form()

    # -----------------------------
    # โหลดสินค้าเดิมเข้าแบบแก้ไข
    # -----------------------------
    def _load_product(self, pid: int):
        con = db_connect(); cur = con.cursor()
        cur.execute("""
            SELECT id, name, price, stock, category, description, image_path
            FROM products
            WHERE id=?
        """, (pid,))
        row = cur.fetchone()
        con.close()

        if not row:
            self.lbl_msg.configure(text="ไม่พบสินค้า", text_color="red")
            return

        self.current_pid = row[0]
        name_val  = row[1] or ""
        price_val = row[2] or 0
        stock_val = row[3] or 0
        cat_val   = (row[4] or "all").lower()
        desc_val  = row[5] or ""
        img_val   = row[6] or ""

        self.current_desc = desc_val
        self.original_image_path = img_val if img_val else None
        self.image_path = None  # ยังไม่เลือกใหม่

        # กรอกฟิลด์
        self.ed_name.delete(0, "end");  self.ed_name.insert(0, name_val)
        self.ed_price.delete(0, "end"); self.ed_price.insert(0, str(price_val))
        self.ed_stock.delete(0, "end"); self.ed_stock.insert(0, str(stock_val))

        if cat_val not in ["all", "combo", "size s", "beverage"]:
            cat_val = "all"
        self.cat_var.set(cat_val)

        # พรีวิวรูป
        img_to_show = self.original_image_path
        if img_to_show and os.path.exists(img_to_show):
            try:
                pil_img = Image.open(img_to_show)
                self._set_preview_from_pil(pil_img)
            except Exception:
                self._set_preview_from_pil(None)
        else:
            self._set_preview_from_pil(None)

        self.lbl_msg.configure(text=f"กำลังแก้ไขสินค้า ID {self.current_pid}", text_color="white")
        self.btn_delete.configure(state="normal")

    # -----------------------------
    # บันทึกสินค้า
    # -----------------------------
    def _save_product(self):
        name_val  = self.ed_name.get().strip()
        price_txt = self.ed_price.get().strip()
        stock_txt = self.ed_stock.get().strip()
        cat_val   = self.cat_var.get().strip().lower()

        desc_val = "" if self.current_pid is None else (self.current_desc or "")

        # รูปที่จะเซฟ: ถ้าเพิ่งเลือกใหม่ → ใช้รูปใหม่, ไม่งั้นใช้รูปเดิม
        final_img_path = self.image_path or (self.original_image_path or "")

        if not name_val:
            self.lbl_msg.configure(text="กรุณากรอกชื่อสินค้า", text_color="red")
            return
        try:
            price_val = float(price_txt)
        except ValueError:
            self.lbl_msg.configure(text="กรุณากรอกราคาเป็นตัวเลข", text_color="red")
            return
        try:
            stock_val = int(stock_txt)
        except ValueError:
            self.lbl_msg.configure(text="กรุณากรอกสต๊อกเป็นจำนวนเต็ม", text_color="red")
            return

        con = db_connect(); cur = con.cursor()
        if self.current_pid is None:
            # INSERT
            cur.execute("""
                INSERT INTO products(name, description, price, stock, category, image_path)
                VALUES(?,?,?,?,?,?)
            """, (name_val, desc_val, price_val, stock_val, cat_val, final_img_path))
            con.commit(); con.close()

            self.lbl_msg.configure(text="เพิ่มสินค้าใหม่เรียบร้อย", text_color="green")
            self.refresh_product_list()
            self._clear_form()
        else:
            # UPDATE
            cur.execute("""
                UPDATE products
                SET name=?,
                    description=?,
                    price=?,
                    stock=?,
                    category=?,
                    image_path=?
                WHERE id=?
            """, (name_val, desc_val, price_val, stock_val, cat_val, final_img_path, self.current_pid))
            con.commit(); con.close()

            self.lbl_msg.configure(text=f"อัปเดตสินค้า ID {self.current_pid} สำเร็จ", text_color="green")
            self.refresh_product_list()
            self._load_product(self.current_pid)  # โหลดกลับมาแสดงผลล่าสุด

    # -----------------------------
    # ลบสินค้า
    # -----------------------------
    def _delete_product(self):
        if self.current_pid is None:
            return

        ok = messagebox.askyesno("ยืนยันการลบ",
                                 f"ต้องการลบสินค้า ID {self.current_pid} จริงหรือไม่?\n(ข้อมูลจะหายไปเลย)")
        if not ok:
            return

        pid_to_delete = self.current_pid
        con = db_connect(); cur = con.cursor()
        cur.execute("DELETE FROM products WHERE id=?", (pid_to_delete,))
        con.commit(); con.close()

        self.lbl_msg.configure(text=f"ลบสินค้า ID {pid_to_delete} แล้ว", text_color="yellow")
        self.refresh_product_list()
        self._clear_form()


class SalesReportPage(ctk.CTkFrame):
    """
    หน้ารายงานยอดขาย: ตารางออเดอร์ + ฟิลเตอร์เวลา (ปี/เดือน/วัน/ชั่วโมง/นาที)
    ต้องมีฟังก์ชัน db_connect() และตาราง orders (paid_at, total_price, queue_code, customer_name, ...).
    """

    # ------------------------- INIT UI -------------------------
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self._auto_refresh_job = None  # กัน AttributeError เวลา destroy()

        # เวลาเริ่มต้น: วันนี้ 00:00 ถึง ตอนนี้
        now = datetime.now()
        self.start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
        self.end_dt   = now

        # StringVar สำหรับ OptionMenu
        self.y_from_var = ctk.StringVar(value=str(self.start_dt.year))
        self.m_from_var = ctk.StringVar(value=f"{self.start_dt.month:02d}")
        self.d_from_var = ctk.StringVar(value=f"{self.start_dt.day:02d}")
        self.h_from_var = ctk.StringVar(value="00")
        self.n_from_var = ctk.StringVar(value="00")

        self.y_to_var = ctk.StringVar(value=str(self.end_dt.year))
        self.m_to_var = ctk.StringVar(value=f"{self.end_dt.month:02d}")
        self.d_to_var = ctk.StringVar(value=f"{self.end_dt.day:02d}")
        self.h_to_var = ctk.StringVar(value=f"{self.end_dt.hour:02d}")
        self.n_to_var = ctk.StringVar(value=f"{self.end_dt.minute:02d}")

        # ===== BG =====
        screen_w = getattr(self.app, "WIDTH", 1280)
        screen_h = getattr(self.app, "HEIGHT", 720)
        bg_path  = os.path.join(self.base_dir, "assets", "bg_0.png")
        try:
            pil_bg = Image.open(bg_path).resize((screen_w, screen_h), Image.LANCZOS)
            self.bg_img_ref = ctk.CTkImage(light_image=pil_bg, dark_image=pil_bg, size=(screen_w, screen_h))
            ctk.CTkLabel(self, image=self.bg_img_ref, text="").place(relx=0, rely=0, relwidth=1, relheight=1)
        except Exception:
            self.configure(fg_color="#f7dc5a")

        # หัวเรื่อง
        ctk.CTkLabel(self, text="ยอดขาย", fg_color="#f7dc5a", text_color="black",
                     corner_radius=0, font=ctk.CTkFont(size=22, weight="bold"),
                     width=200, height=46).place(relx=0.5, rely=0.14, anchor="center")

        # ====================== ซ้าย: ตาราง ======================
        left_card = ctk.CTkFrame(self, fg_color="white", corner_radius=16, width=800, height=470)
        left_card.place(relx=0.41, rely=0.56, anchor="center")
        left_card.grid_propagate(False)
        left_card.grid_rowconfigure(1, weight=1)
        left_card.grid_columnconfigure(0, weight=1)

        # สัดส่วนหัวตาราง: เวลา | คิว | user | จำนวนเงิน | รายละเอียด
        self.COL_WEIGHTS = [6, 3, 4, 5, 2]
        self.COL_MINSIZE = [220, 90, 160, 20, 120]

        # หัวตาราง
        hdr = ctk.CTkFrame(left_card, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 6))
        for i, (w, m) in enumerate(zip(self.COL_WEIGHTS, self.COL_MINSIZE)):
            hdr.grid_columnconfigure(i, weight=w, uniform="tbl", minsize=m)

        def H(txt, col, anchor="w", padx=(0, 0)):
            ctk.CTkLabel(
                hdr, text=txt, text_color="black",
                font=ctk.CTkFont(size=20, weight="bold"),
                anchor=anchor
            ).grid(row=0, column=col, sticky=anchor, padx=padx)

        H("เวลา", 0, "w")
        H("คิว", 1, "w")
        H("user", 2, "w")
        H("จำนวนเงิน", 3, "w", padx=(0, 0))
        H(" ", 4, "w")

        # เนื้อหาตาราง
        self.table_scroll = ctk.CTkScrollableFrame(
            left_card, fg_color="white", corner_radius=0, border_width=0, height=360
        )
        self.table_scroll.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 16))
        self.table_scroll.grid_columnconfigure(0, weight=1)

        # ================== ขวา: สรุป & เลือกช่วงเวลา ==================
        right_card = ctk.CTkFrame(self, fg_color="white", corner_radius=0, width=380, height=480)
        right_card.place(relx=0.82, rely=0.54, anchor="center")
        right_card.grid_propagate(False)

        # โลโก้ + หัว
        logo_path = os.path.join(self.base_dir, "assets", "logo.png")
        try:
            pil_logo = Image.open(logo_path).resize((84, 84), Image.LANCZOS)
        except Exception:
            pil_logo = Image.new("RGBA", (84, 84), (255, 215, 0, 255))
        self.logo_ref = ctk.CTkImage(light_image=pil_logo, dark_image=pil_logo, size=(84, 84))
        ctk.CTkLabel(right_card, image=self.logo_ref, text="").pack(pady=(16, 4))
        ctk.CTkLabel(right_card, text="สรุปยอดขาย", text_color="black",
                     font=ctk.CTkFont(size=22, weight="bold")).pack()

        time_box = ctk.CTkFrame(right_card, fg_color="transparent")
        time_box.pack(fill="x", pady=(8, 8), padx=24)

        years  = [str(y) for y in range(self.end_dt.year-2, self.end_dt.year+6)]
        months = [f"{m:02d}" for m in range(1, 13)]
        days   = [f"{d:02d}" for d in range(1, 32)]
        hours  = [f"{h:02d}" for h in range(24)]
        mins   = [f"{m:02d}" for m in range(60)]

        # ตั้งแต่
        row_from = ctk.CTkFrame(time_box, fg_color="transparent"); row_from.pack(fill="x", pady=(6, 4))
        ctk.CTkLabel(row_from, text="ตั้งแต่", text_color="black",
                     font=ctk.CTkFont(size=16, weight="bold"), width=60, anchor="w").pack(side="left")
        ctk.CTkOptionMenu(row_from, values=years,  width=70, variable=self.y_from_var).pack(side="left", padx=(6, 4))
        ctk.CTkOptionMenu(row_from, values=months, width=60, variable=self.m_from_var).pack(side="left", padx=(0, 4))
        ctk.CTkOptionMenu(row_from, values=days,   width=60, variable=self.d_from_var).pack(side="left", padx=(0, 8))
        ctk.CTkOptionMenu(row_from, values=hours,  width=60, variable=self.h_from_var).pack(side="left", padx=(0, 4))
        ctk.CTkOptionMenu(row_from, values=mins,   width=60, variable=self.n_from_var).pack(side="left")

        # จนถึง
        row_to = ctk.CTkFrame(time_box, fg_color="transparent"); row_to.pack(fill="x", pady=(8, 10))
        ctk.CTkLabel(row_to, text="จนถึง", text_color="black",
                     font=ctk.CTkFont(size=16, weight="bold"), width=60, anchor="w").pack(side="left")
        ctk.CTkOptionMenu(row_to, values=years,  width=70, variable=self.y_to_var).pack(side="left", padx=(6, 4))
        ctk.CTkOptionMenu(row_to, values=months, width=60, variable=self.m_to_var).pack(side="left", padx=(0, 4))
        ctk.CTkOptionMenu(row_to, values=days,   width=60, variable=self.d_to_var).pack(side="left", padx=(0, 8))
        ctk.CTkOptionMenu(row_to, values=hours,  width=60, variable=self.h_to_var).pack(side="left", padx=(0, 4))
        ctk.CTkOptionMenu(row_to, values=mins,   width=60, variable=self.n_to_var).pack(side="left")

        ctk.CTkButton(right_card, text="อัปเดตช่วงเวลา", width=200, height=38,
                      fg_color="#108a5a", hover_color="#0a5839", text_color="white",
                      command=self._apply_filter).pack(pady=(6, 10))

        ctk.CTkLabel(right_card, text="------------------------------",
                     text_color="#555", font=ctk.CTkFont(size=14)).pack(pady=(0, 6))

        self.lbl_orders = ctk.CTkLabel(right_card, text="จำนวนออเดอร์: 0 ออเดอร์",
                                       text_color="black", font=ctk.CTkFont(size=16, weight="bold"))
        self.lbl_orders.pack(pady=(2, 2))
        self.lbl_sum = ctk.CTkLabel(right_card, text="รายรับทั้งหมด: 0 บาท",
                                    text_color="black", font=ctk.CTkFont(size=16, weight="bold"))
        self.lbl_sum.pack()

        # ปุ่มย้อนกลับ
        ctk.CTkButton(self, text="ย้อนกลับ", width=140, height=40,
                      fg_color="#c41216", hover_color="#800000", text_color="white",
                      corner_radius=0, font=ctk.CTkFont(size=16, weight="bold"),
                      command=lambda: self.app.show_page("adminmenu") if hasattr(self.app, "show_page") else None)\
            .place(relx=0.92, rely=0.94, anchor="center")

        # โหลดครั้งแรก
        self._apply_filter()
    def _net_total_for_order(self, order_id: int) -> float:
        """
        คำนวณ 'ยอดสุทธิ' ของออเดอร์ = SUM(qty*unit_price) * 1.07
        (ดึงจาก order_items โดยตรง เพื่อให้แน่ใจว่าเป็นยอดหลังบวก VAT 7%)
        """
        try:
            con = db_connect(); cur = con.cursor()
            cur.execute("SELECT COALESCE(SUM(qty*unit_price), 0) FROM order_items WHERE order_id=?", (order_id,))
            subtotal = float(cur.fetchone()[0] or 0.0)
        finally:
            try: con.close()
            except Exception: pass
        return round(subtotal * 1.07, 2)

    # 1) ใช้ช่วงเวลาที่ผู้ใช้ตั้งไว้ "ตามจริง" ไม่เขียนทับค่า 'จนถึง' เป็นเวลาปัจจุบัน
    def _apply_filter(self):
        # อ่านช่วงเวลาจาก OptionMenu ตามที่ผู้ใช้ตั้งไว้
        y1, m1, d1 = int(self.y_from_var.get()), int(self.m_from_var.get()), int(self.d_from_var.get())
        h1, n1     = int(self.h_from_var.get()), int(self.n_from_var.get())
        y2, m2, d2 = int(self.y_to_var.get()),   int(self.m_to_var.get()),   int(self.d_to_var.get())
        h2, n2     = int(self.h_to_var.get()),   int(self.n_to_var.get())

        dt_from = datetime(y1, m1, d1, h1, n1, 0)
        dt_to   = datetime(y2, m2, d2, h2, n2, 59)
        if dt_from > dt_to:
            dt_from, dt_to = dt_to, dt_from

        orders = self._load_orders(dt_from, dt_to)   # ← ดึงยอดสุทธิรวม VAT ต่อบิลเรียบร้อย
        self._populate_table(orders)                 # ← อัปเดต “ตารางฝั่งซ้าย” ให้ตรงช่วงเวลา

    # 2) โหลดยอดสุทธิจาก DB ตามช่วงเวลา (เหมือนเดิมได้เลย)
    def _load_orders(self, dt_from, dt_to):
        """ดึงรายการออเดอร์ตามช่วงเวลา
        - รวมยอดสุทธิ (subtotal*1.07) ต่อบิล
        - แนบ path ของใบเสร็จ PDF และสลิป (ถ้ามีคอลัมน์ในตาราง)
        """
        sql_from = dt_from.strftime("%Y-%m-%d %H:%M:%S")
        sql_to   = dt_to.strftime("%Y-%m-%d %H:%M:%S")

        con = db_connect(); cur = con.cursor()

        # เช็คว่าตาราง orders มีคอลัมน์อะไรบ้าง (กัน error ถ้าเครื่องใดยังไม่มีคอลัมน์ใหม่)
        cur.execute("PRAGMA table_info(orders)")
        order_cols = [r[1] for r in cur.fetchall()]
        has_pdf  = "receipt_pdf_path" in order_cols
        has_slip = "slip_path" in order_cols

        # สร้าง SELECT แบบ dynamic ตามคอลัมน์ที่มีจริง
        select_cols = [
            "o.id",
            "o.queue_code",
            "o.customer_name",
            "o.paid_at",
            "ROUND(COALESCE(SUM(oi.qty * oi.unit_price), 0) * 1.07, 2) AS net_total",
        ]
        if has_pdf:
            select_cols.append("o.receipt_pdf_path")
        if has_slip:
            select_cols.append("o.slip_path")

        sql = f"""
            SELECT {", ".join(select_cols)}
            FROM orders o
            LEFT JOIN order_items oi ON oi.order_id = o.id
            WHERE datetime(o.paid_at) BETWEEN ? AND ?
            GROUP BY o.id
            ORDER BY datetime(o.paid_at) DESC
        """

        cur.execute(sql, (sql_from, sql_to))
        rows = cur.fetchall()
        con.close()

        # map index -> key ให้ตรงกับ select_cols ข้างบน
        base_keys = ["id", "queue_code", "customer_name", "paid_at", "net_total"]
        if has_pdf:
            base_keys.append("receipt_pdf_path")
        if has_slip:
            base_keys.append("slip_path")

        out = []
        for r in rows:
            d = {base_keys[i]: r[i] for i in range(len(base_keys))}
            # ปกป้องค่า None / แปลงประเภท
            d["net_total"] = float(d.get("net_total") or 0.0)
            if not has_pdf:
                d["receipt_pdf_path"] = None
            if not has_slip:
                d["slip_path"] = None
            out.append(d)

        return out


    # 3) วาดตารางฝั่งซ้ายให้เป็นยอดสุทธิรวม VAT และสรุปรวมทางขวา
    def _populate_table(self, orders: list[dict]) -> None:
        for w in self.table_scroll.winfo_children():
            w.destroy()

        if not orders:
            ctk.CTkLabel(self.table_scroll, text="(ไม่พบออเดอร์ในช่วงที่เลือก)",
                        text_color="black", font=ctk.CTkFont(size=16, weight="bold"),
                        anchor="w").grid(row=0, column=0, sticky="w", padx=20, pady=8)
            if hasattr(self, "lbl_orders"):
                self.lbl_orders.configure(text="จำนวนออเดอร์: 0 ออเดอร์")
            if hasattr(self, "lbl_sum"):
                self.lbl_sum.configure(text="รายรับทั้งหมด: 0 บาท")
            return

        COL_WEIGHTS = [8, 3, 7, 4, 2]   # เวลา, คิว, user, จำนวนเงิน(สุทธิ), ปุ่ม
        COL_MINSIZE = [220, 80, 200, 120, 120]

        total_amount = 0.0
        for i, od in enumerate(orders):
            row = ctk.CTkFrame(self.table_scroll, fg_color="white", corner_radius=10)
            row.grid(row=i, column=0, sticky="ew", padx=(0, 18), pady=4)
            for c in range(5):
                row.grid_columnconfigure(c, weight=COL_WEIGHTS[c], minsize=COL_MINSIZE[c], uniform="tbl")
            row.grid_columnconfigure(5, weight=0, minsize=1)

            paid_at = od.get("paid_at") or "-"
            queue   = od.get("queue_code") or "-"
            user    = od.get("customer_name") or "-"
            amount  = float(od.get("net_total") or 0.0)
            total_amount += amount

            ctk.CTkLabel(row, text=paid_at, anchor="w", text_color="black")\
                .grid(row=0, column=0, sticky="w", padx=(12, 6))
            ctk.CTkLabel(row, text=queue,   anchor="w", text_color="black")\
                .grid(row=0, column=1, sticky="w", padx=6)
            ctk.CTkLabel(row, text=user,    anchor="w", text_color="black")\
                .grid(row=0, column=2, sticky="w", padx=6)
            ctk.CTkLabel(row, text=f"{amount:,.0f}", anchor="w", text_color="black")\
                .grid(row=0, column=3, sticky="w", padx=(6, 0))

            ctk.CTkButton(
                row, text="ดูรายละเอียด", width=120, height=32,
                fg_color="#1a73e8", hover_color="#1558b0", text_color="white", corner_radius=8,
                command=lambda data=od: self._show_detail_dialog(data)
            ).grid(row=0, column=4, sticky="e", padx=(6, 12))

        if hasattr(self, "lbl_orders"):
            self.lbl_orders.configure(text=f"จำนวนออเดอร์: {len(orders)} ออเดอร์")
        if hasattr(self, "lbl_sum"):
            self.lbl_sum.configure(text=f"รายรับทั้งหมด: {total_amount:,.0f} บาท")


    def _show_detail_dialog(self, order: dict):
        import os, sys, subprocess
        from tkinter import messagebox

        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        RECEIPTS_DIR = os.path.join(BASE_DIR, "receipts")
        os.makedirs(RECEIPTS_DIR, exist_ok=True)

        def _resolve_file(p, *roots):
            if not p: return None
            if os.path.isabs(p) and os.path.exists(p): return p
            for r in roots:
                cand = os.path.join(r, p)
                if os.path.exists(cand):
                    return cand
            return None

        pdf_raw  = (order.get("receipt_pdf_path") or order.get("receipt_pdf") or order.get("receipt_path") or "")
        slip_raw = (order.get("slip_path")        or order.get("slip")        or order.get("payment_slip")  or "")

        receipt_pdf = _resolve_file(pdf_raw, RECEIPTS_DIR, BASE_DIR)
        slip_file   = _resolve_file(slip_raw, os.path.join(BASE_DIR, "user_pics"), RECEIPTS_DIR, BASE_DIR)

        # ---------- Window (Modal) ----------
        win = ctk.CTkToplevel(self)
        win.title(f"รายละเอียดออเดอร์ {order.get('queue_code','')}")
        win.geometry("980x640")
        win.transient(self.winfo_toplevel())
        win.grab_set()
        win.protocol("WM_DELETE_WINDOW", win.destroy)

        root = ctk.CTkFrame(win, fg_color="black")
        root.pack(fill="both", expand=True, padx=12, pady=12)
        root.grid_columnconfigure(0, weight=1); root.grid_columnconfigure(1, weight=1)
        root.grid_rowconfigure(0, weight=1);    root.grid_rowconfigure(1, weight=0)

        # ================== ฝั่งซ้าย: บิล ==================
        left = ctk.CTkFrame(root, fg_color="#FFFFFF", corner_radius=10)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        header = ctk.CTkFrame(left, fg_color="white")
        header.pack(fill="x", padx=12, pady=(12, 6))

        paid_at_txt = order.get("paid_at") or order.get("created_at") or ""
        try:
            dt = datetime.strptime(paid_at_txt, "%Y-%m-%d %H:%M:%S")
            nice_date = dt.strftime("%d/%m/%Y")
            nice_time = dt.strftime("%H:%M")
        except Exception:
            nice_date, nice_time = paid_at_txt, ""

        ctk.CTkLabel(header, text="บิล", text_color="black",
                     font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(header, text=f"คิว: {order.get('queue_code','-')}", text_color="black").grid(row=1, column=0, sticky="w")
        ctk.CTkLabel(header, text=f"ชื่อลูกค้า: {order.get('customer_name','-')}", text_color="black").grid(row=2, column=0, sticky="w")
        ctk.CTkLabel(header, text=f"วันที่: {nice_date}    เวลา: {nice_time}", text_color="black").grid(row=3, column=0, sticky="w")

        bill_box = ctk.CTkScrollableFrame(left, fg_color="white")
        bill_box.pack(fill="both", expand=True, padx=12, pady=(6, 12))
        for i in range(4):
            bill_box.grid_columnconfigure(i, weight=(3 if i == 0 else 1))

        heads = ("รายการ", "จำนวน", "ราคา/หน่วย", "รวม")
        for j, t in enumerate(heads):
            ctk.CTkLabel(bill_box, text=t, text_color="black",
                         font=ctk.CTkFont(size=13, weight="bold")).grid(row=0, column=j,
                         sticky=("w","e","e","e")[j], padx=(0,6), pady=(0,4))

        rows = []
        order_pk = order.get("id") or order.get("order_id")
        if order_pk is not None:
            try:
                con = db_connect(); cur = con.cursor()
                cur.execute("""
                    SELECT COALESCE(p.name,''), oi.qty, oi.unit_price, (oi.qty*oi.unit_price)
                    FROM order_items oi
                    LEFT JOIN products p ON p.id = oi.product_id
                    WHERE oi.order_id=? ORDER BY oi.id
                """, (order_pk,))
                rows = cur.fetchall()
            finally:
                try: con.close()
                except: pass

        subtotal = 0.0
        for r, (name, qty, unit_price, line_total) in enumerate(rows, start=1):
            subtotal += float(line_total or 0)
            ctk.CTkLabel(bill_box, text=str(name),                   text_color="black").grid(row=r, column=0, sticky="w")
            ctk.CTkLabel(bill_box, text=f"x{int(qty)}",              text_color="black").grid(row=r, column=1, sticky="e")
            ctk.CTkLabel(bill_box, text=f"{float(unit_price):,.0f}", text_color="black").grid(row=r, column=2, sticky="e")
            ctk.CTkLabel(bill_box, text=f"{float(line_total):,.0f}", text_color="black").grid(row=r, column=3, sticky="e")

        vat   = round(subtotal * 0.07, 2)
        total = round(subtotal + vat, 2)

        sum_box = ctk.CTkFrame(left, fg_color="white")
        sum_box.pack(fill="x", padx=12, pady=(0, 12))
        sum_box.grid_columnconfigure(0, weight=1)
        for i, (label, val) in enumerate((
            ("จำนวนเงินรวม", subtotal),
            ("ภาษี 7%",      vat),
            ("เงินสุทธิ",     total),
        )):
            rowf = ctk.CTkFrame(sum_box, fg_color="white")
            rowf.grid(row=i, column=0, sticky="e", pady=(0,2))
            ctk.CTkLabel(rowf, text=f"{label} :", text_color="black").pack(side="left")
            ctk.CTkLabel(rowf, text=f"{val:,.0f} บาท", text_color="black",
                         font=ctk.CTkFont(size=13, weight=("bold" if label=="เงินสุทธิ" else "normal"))).pack(side="left", padx=(6,0))

        if receipt_pdf:
            btn_bar = ctk.CTkFrame(left, fg_color="white")
            btn_bar.pack(fill="x", padx=12, pady=(0, 8))
            def _open_pdf():
                try:
                    if os.name == "nt":
                        os.startfile(receipt_pdf)
                    elif sys.platform == "darwin":
                        subprocess.call(["open", receipt_pdf])
                    else:
                        subprocess.call(["xdg-open", receipt_pdf])
                except Exception as e:
                    messagebox.showerror("เปิดไฟล์ไม่ได้", f"{receipt_pdf}\n{e}")
            ctk.CTkButton(btn_bar, text="เปิดบิล (PDF)", width=140,
                          fg_color="#1769aa", hover_color="#0e4977",
                          command=_open_pdf).pack(side="right")

        # ================== ฝั่งขวา: สลิป ==================
        right = ctk.CTkFrame(root, fg_color="#FFFFFF", corner_radius=10)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            right, text="สลิปโอน", text_color="black",
            font=ctk.CTkFont(size=16, weight="bold")
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 6))

        slip_scroll = ctk.CTkScrollableFrame(right, fg_color="white")
        slip_scroll.grid(row=1, column=0, sticky="nsew", padx=(0, 12), pady=(0, 12))
        slip_scroll.grid_columnconfigure(0, weight=1)

        slip_img_label = ctk.CTkLabel(
            slip_scroll,
            text="(ไม่มีไฟล์สลิป)" if not slip_file else "กำลังโหลดสลิป...",
            text_color="#777777",
            anchor="n",
        )
        slip_img_label.grid(row=0, column=0, sticky="nw", padx=0, pady=0)

        pil_original = None
        if slip_file and os.path.exists(slip_file):
            try:
                pil_original = Image.open(slip_file).convert("RGBA")
            except Exception as e:
                pil_original = None
                slip_img_label.configure(text=f"โหลดสลิปไม่สำเร็จ: {e}", text_color="red")

        SHRINK = 0.85
        SIDE_PAD = 12
        TOP_FOOT = 60

        def _available_rect():
            right.update_idletasks()
            aw = max(50, right.winfo_width()  - (SIDE_PAD + 6 + 12))
            ah = max(50, right.winfo_height() - TOP_FOOT)
            return aw, ah

        def _render_fit_width(pil_img):
            if pil_img is None:
                slip_img_label.configure(text="(ไม่มีไฟล์สลิป)", image=None)
                return
            aw, ah = _available_rect()
            ratio = min(aw / pil_img.width, ah / pil_img.height) * SHRINK
            ratio = max(ratio, 0.1)
            w = int(pil_img.width  * ratio)
            h = int(pil_img.height * ratio)
            disp = pil_img.resize((w, h), Image.LANCZOS)
            img  = ctk.CTkImage(light_image=disp, dark_image=disp, size=(w, h))
            self._detail_img_refs = getattr(self, "_detail_img_refs", [])
            self._detail_img_refs.append(img)
            slip_img_label.configure(image=img, text="")
            slip_img_label.grid_configure(sticky="nw")

        right.bind("<Configure>", lambda e: _render_fit_width(pil_original))
        slip_scroll.bind("<Configure>", lambda e: _render_fit_width(pil_original))
        slip_img_label.after(80, lambda: _render_fit_width(pil_original))


# =========================================================
# ====================   APP CORE   =======================
# =========================================================
class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        # -------------------- 0) เตรียมขนาดหน้าจอ --------------------
        self.WIDTH  = self.winfo_screenwidth()
        self.HEIGHT = self.winfo_screenheight()
        self.geometry(f"{self.WIDTH}x{self.HEIGHT}+0+0")

        # พยายามขยายเต็มหน้าจอ
        try:
            self.state("zoomed")
        except Exception:
            self.attributes("-fullscreen", True)
        self.after(200, self._force_fullscreen)

        # -------------------- 1) container หลัก --------------------
        self.container = ctk.CTkFrame(self, fg_color="black")
        self.container.pack(fill="both", expand=True)

        # -------------------- 2) session กลางของแอป --------------------
        self.current_user = None
        self.cart = {}            # ตะกร้ามีแน่นอนตั้งแต่เริ่ม
        self.receipt_info = {}

        # เก็บชื่อหน้าปัจจุบัน (ไว้ยิง on_hide)
        self._current_page = None

        # -------------------- 3) สร้างหน้าทั้งหมด --------------------
        self.pages = {}
        self.pages["login"]        = LoginPage(self.container, self)
        self.pages["register"]     = RegisterPage(self.container, self)
        self.pages["resetpw"]      = ResetPasswordPage(self.container, self)
        self.pages["customermenu"] = CustomerMenuPage(self.container, self)
        self.pages["basket"]       = BasketPage(self.container, self)
        self.pages["profile"]      = ProfilePage(self.container, self)
        self.pages["info"]         = InfoPage(self.container, self)
        self.pages["adminmenu"]    = AdminMenuPage(self.container, self)
        self.pages["stock"]        = ProductManagePage(self.container, self)
        self.pages["sales"]        = SalesReportPage(self.container, self)
        self.pages["payment"]      = PaymentPage(self.container, self)
        self.pages["receipt"]      = ReceiptPage(self.container, self)

        # -------------------- 4) วางทุกหน้าเต็ม container --------------------
        for p in self.pages.values():
            p.place(relx=0, rely=0, relwidth=1, relheight=1)

        # -------------------- 5) โชว์หน้าแรก --------------------
        self.show_page("login")

    # -------------------- utilities --------------------
    def _force_fullscreen(self):
        try:
            self.state("zoomed")
        except Exception:
            self.attributes("-fullscreen", True)
        self.update_idletasks()

    def get_page(self, name: str):
        return self.pages.get(name)

    # -------------------- สลับหน้าแบบปลอดภัย --------------------
    def show_page(self, name: str):
        # on_hide หน้าเดิม (ถ้ามี)
        if self._current_page:
            old_page = self.pages.get(self._current_page)
            if old_page:
                # ยกเลิกงาน after ที่อาจค้าง (เช่น auto refresh)
                job = getattr(old_page, "_auto_refresh_job", None)
                if job and hasattr(old_page, "after_cancel"):
                    try:
                        old_page.after_cancel(job)
                    except Exception:
                        pass
                    setattr(old_page, "_auto_refresh_job", None)

                if hasattr(old_page, "on_hide"):
                    try:
                        old_page.on_hide()
                    except Exception:
                        pass

        # แสดงหน้าใหม่
        page = self.pages[name]
        page.tkraise()

        # on_show หน้าใหม่ (ถ้ามี)
        if hasattr(page, "on_show"):
            try:
                page.on_show()
            except Exception:
                pass

        # restart auto refresh ถ้าหน้ารองรับ
        if hasattr(page, "_start_auto_refresh"):
            try:
                page._start_auto_refresh()
            except Exception:
                pass

        # refresh ทั่วไป
        if hasattr(page, "refresh"):
            try:
                page.refresh()
            except Exception:
                pass

        # refresh เฉพาะส่วนที่คุณระบุ
        if name == "basket" and hasattr(self.pages["basket"], "refresh"):
            self.pages["basket"].refresh()
        if name == "customermenu" and hasattr(self.pages["customermenu"], "profile_header"):
            self.pages["customermenu"].profile_header.refresh()

        self._current_page = name

    # -------------------- ตะกร้าสินค้า (helpers) --------------------
    def add_to_cart(self, pid: int, name: str, price: float, qty: int = 1):
        if qty <= 0:
            qty = 1
        if pid not in self.cart:
            self.cart[pid] = {"name": name, "price": float(price), "qty": 0}
        self.cart[pid]["qty"] += int(qty)
        page = self.get_page("basket")
        if page and hasattr(page, "refresh"):
            page.refresh()

    def update_cart_qty(self, pid: int, qty: int):
        if pid in self.cart:
            if qty <= 0:
                del self.cart[pid]
            else:
                self.cart[pid]["qty"] = int(qty)
        page = self.get_page("basket")
        if page and hasattr(page, "refresh"):
            page.refresh()

    def remove_from_cart(self, pid: int):
        if pid in self.cart:
            del self.cart[pid]
        page = self.get_page("basket")
        if page and hasattr(page, "refresh"):
            page.refresh()

    def clear_cart(self):
        self.cart.clear()
        page = self.get_page("basket")
        if page and hasattr(page, "refresh"):
            page.refresh()


# =========================================================
# =====================   RUN APP   =======================
# =========================================================
if __name__ == "__main__":
    init_db()
    app = App()
    app.mainloop()
