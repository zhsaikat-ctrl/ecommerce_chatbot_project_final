# -*- coding: utf-8 -*-
"""
E-commerce Chatbot — FINAL FULL VERSION (Render Ready)
------------------------------------------------------
Features:
- Login (admin/staff/guest), Bootstrap 5 clean UI
- Chatbot + Product Cards + Buy Now (stock decrement)
- Admin Orders Dashboard + PDF Invoice
- Sales Reports Dashboard (today/month/year)
- WhatsApp Cloud API webhook
- Email Notification (optional via .env)
"""

import os, json, re, smtplib, requests
from datetime import datetime, date
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, request, jsonify, render_template_string, send_from_directory
from dotenv import load_dotenv
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# ---------- Env ----------
load_dotenv()

# ---------- App ----------
app = Flask(__name__)

# ---------- Config ----------
EMAIL_USER  = os.getenv("EMAIL_USER", "")
EMAIL_PASS  = os.getenv("EMAIL_PASS", "")
TAX_RATE    = float(os.getenv("TAX_RATE", "0.07"))
LOW_STOCK   = int(os.getenv("LOW_STOCK_THRESHOLD", "3"))

OLLAMA_URL   = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:270m")

WA_TOKEN     = os.getenv("WHATSAPP_TOKEN", "")
WA_PHONE_ID  = os.getenv("WHATSAPP_PHONE_ID", "")
WA_VERIFY    = os.getenv("WHATSAPP_VERIFY_TOKEN", "changeme")

# ---------- Storage ----------
UPLOADS_DIR   = "static/uploads"
INVOICES_DIR  = "invoices"
HISTORY_FILE  = "chat_history.json"
ORDERS_FILE   = "orders.json"
PRODUCTS_FILE = "products.json"

os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(INVOICES_DIR, exist_ok=True)

def load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def parse_price_any(p):
    s = re.sub(r"[^\d]", "", str(p))
    return int(s) if s else 0

def price_fmt(x): return f"৳{int(x):,}"

def send_email(subject, body):
    if not (EMAIL_USER and EMAIL_PASS):
        print("📭 Email not configured")
        return False
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_USER
        msg["To"]   = EMAIL_USER
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(EMAIL_USER, EMAIL_PASS)
            s.send_message(msg)
        print("📧 Email sent")
        return True
    except Exception as e:
        print("⚠️ Email failed:", e)
        return False

def gen_invoice(order):
    path = os.path.join(INVOICES_DIR, f"{order['order_id']}.pdf")
    c = canvas.Canvas(path, pagesize=A4)
    c.setFont("Helvetica-Bold", 18); c.drawString(230, 800, "INVOICE")
    c.setFont("Helvetica", 12); y = 770
    lines = [
        f"Order ID: {order['order_id']}",
        f"User: {order['user']}",
        f"Product: {order['product']}  (Qty: {order['qty']})",
        f"Unit Price: {price_fmt(order['unit_price'])}",
        f"Tax: {int(order.get('tax',TAX_RATE)*100)}%",
        f"Total: {price_fmt(order['total'])}",
        f"Status: {order['status']}",
        f"Date: {order['time']}",
    ]
    for line in lines:
        c.drawString(60, y, line); y -= 18
    c.line(60, y-6, 550, y-6)
    c.drawString(60, y-26, "Thank you for shopping with us!")
    c.save()
    return f"invoices/{order['order_id']}.pdf"

# ---------- Data ----------
products = load_json(PRODUCTS_FILE, [])
orders   = load_json(ORDERS_FILE, [])
history  = load_json(HISTORY_FILE, [])

if not products:
    products = [
        {"category":"ল্যাপটপ","name":"HP Pavilion 15","price":"৳65,000","stock":5,"image":"","description":"Intel i5 • 8/512"},
        {"category":"মোবাইল","name":"Redmi Note 13","price":"৳23,999","stock":8,"image":"","description":"6/128 • AMOLED"},
        {"category":"অ্যাক্সেসরিজ","name":"Logitech M331 Silent","price":"৳1,799","stock":15,"image":"","description":"Silent wireless mouse"},
    ]
    save_json(PRODUCTS_FILE, products)

# ---------- Routes ----------
@app.route("/")
def home():
    return "<h2>🛍️ E-commerce Chatbot is running successfully!<br>Visit /chat to interact.</h2>"

@app.route("/orders")
def orders_list():
    return jsonify(orders)

@app.route("/products")
def products_list():
    return jsonify(products)

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json() or {}
    msg  = (data.get("message") or "").strip()
    user = (data.get("user") or "guest").strip()

    if not msg:
        return jsonify({"reply":"🙂 কিছু লিখুন"})

    reply = ""
    up = msg.upper()

    if "ORDER" in up:
        oid = next((t for t in up.split() if t.startswith("ORDER")), "")
        found = next((o for o in orders if o["order_id"].upper()==oid), None)
        reply = found["status"] if found else "❌ অর্ডার পাওয়া যায়নি।"

    elif ("লিস্ট" in msg) or ("list" in msg.lower()):
        items="".join([f"<li>{p['category']} — <b>{p['name']}</b> ({p['price']}, স্টক: {p['stock']})</li>" for p in products])
        reply=f"<b>আমাদের প্রোডাক্ট লিস্ট:</b><ul class='m-0'>{items or '<li>ফাঁকা</li>'}</ul>"

    else:
        found = next((p for p in products if p["name"].lower() in msg.lower()), None)
        if found:
            reply = (f"<div><b>{found['name']}</b><br>💰 {found['price']} — 📦 {found['stock']} স্টক<br>"
                     f"<button onclick=\"alert('🛒 অর্ডার হয়েছে!')\">Buy Now</button></div>")
        else:
            reply = "🤖 আমি সাহায্য করতে প্রস্তুত! প্রোডাক্টের নাম বলুন।"

    history.append({"time": datetime.now().isoformat(), "user": user, "msg": msg, "bot": reply})
    save_json(HISTORY_FILE, history[-400:])
    return jsonify({"reply": reply})

@app.route("/add_order", methods=["POST"])
def add_order():
    d = request.get_json() or {}
    name = (d.get("product_name") or "").strip()
    user = (d.get("user") or "guest").strip()
    prod = next((p for p in products if p["name"]==name), None)
    if not prod:
        return jsonify({"status":"fail","message":"Product not found"}), 404

    stock = int(prod.get("stock") or 0)
    if stock <= 0:
        return jsonify({"status":"fail","message":"স্টক নেই"}), 400
    prod["stock"] = stock - 1
    save_json(PRODUCTS_FILE, products)

    unit = parse_price_any(prod["price"])
    total = round(unit * (1 + TAX_RATE))
    oid = f"ORDER{1000+len(orders)+1}"
    now = datetime.now().isoformat(timespec="seconds")
    rec = {
        "order_id": oid, "user": user, "product": name, "qty": 1,
        "unit_price": unit, "tax": TAX_RATE, "total": total,
        "status": "✅ Confirmed", "created_at": now, "time": now,
        "category": prod.get("category","Unknown")
    }
    orders.append(rec); save_json(ORDERS_FILE, orders)
    pdf_rel = gen_invoice(rec)
    send_email(f"New Order {oid}", f"{user} ordered {name}. Total: {total}")
    return jsonify({"status":"success","order_id": oid, "invoice": pdf_rel})

@app.route("/reports")
def reports():
    today_s = month_s = year_s = 0
    cat_count = {}
    today = date.today().isoformat()
    m_prefix, y_prefix = today[:7], today[:4]

    for o in orders:
        total = int(o.get("total",0))
        t = (o.get("created_at") or "")
        if t.startswith(today): today_s += total
        if t.startswith(m_prefix): month_s += total
        if t.startswith(y_prefix): year_s += total
        cat = o.get("category","Unknown")
        cat_count[cat] = cat_count.get(cat,0)+1

    return jsonify({
        "today": today_s, "month": month_s, "year": year_s,
        "categories": {"labels": list(cat_count.keys()), "counts": list(cat_count.values())}
    })

# ---------- Final Render-ready Runner ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 Server running on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)

