# -*- coding: utf-8 -*-
"""
E-commerce Chatbot — Render Fixed Version
-----------------------------------------
Now supports browser GET /chat (UI)
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

# ---------- Data ----------
ORDERS_FILE   = "orders.json"
PRODUCTS_FILE = "products.json"
HISTORY_FILE  = "chat_history.json"
INVOICES_DIR  = "invoices"
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
        return True
    except:
        return False

def gen_invoice(order):
    path = os.path.join(INVOICES_DIR, f"{order['order_id']}.pdf")
    c = canvas.Canvas(path, pagesize=A4)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(230, 800, "INVOICE")
    c.setFont("Helvetica", 12)
    y = 770
    for line in [
        f"Order ID: {order['order_id']}",
        f"User: {order['user']}",
        f"Product: {order['product']} (Qty: {order['qty']})",
        f"Total: {price_fmt(order['total'])}",
        f"Status: {order['status']}",
        f"Date: {order['time']}",
    ]:
        c.drawString(60, y, line)
        y -= 18
    c.save()
    return f"invoices/{order['order_id']}.pdf"

# ---------- Load data ----------
products = load_json(PRODUCTS_FILE, [])
orders   = load_json(ORDERS_FILE, [])
history  = load_json(HISTORY_FILE, [])

if not products:
    products = [
        {"category":"ল্যাপটপ","name":"HP Pavilion 15","price":"৳65,000","stock":5},
        {"category":"মোবাইল","name":"Redmi Note 13","price":"৳23,999","stock":8},
        {"category":"অ্যাক্সেসরিজ","name":"Logitech M331","price":"৳1,799","stock":15}
    ]
    save_json(PRODUCTS_FILE, products)

# ---------- Routes ----------
@app.route("/")
def home():
    return "<h2>🛍️ E-commerce Chatbot is running successfully!<br>Go to <a href='/chat'>/chat</a> to interact.</h2>"

# ✅ FIXED: এখন /chat এ গেলে ব্রাউজারে UI খুলবে
@app.route("/chat", methods=["GET", "POST"])
def chat():
    if request.method == "GET":
        # Simple HTML UI
        return """
        <html><head><title>Chatbot</title></head>
        <body style='font-family:sans-serif;background:#fafafa;padding:20px'>
        <h2>🤖 E-commerce Chatbot</h2>
        <form id='f' onsubmit='sendMsg();return false;'>
        <input id='msg' placeholder='Write a message...' style='padding:8px;width:300px'>
        <button>Send</button></form>
        <div id='chat' style='margin-top:20px'></div>
        <script>
        async function sendMsg(){
          let m=document.getElementById('msg').value;
          document.getElementById('msg').value='';
          let d=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:m,user:'guest'})});
          let j=await d.json();
          let c=document.getElementById('chat');
          c.innerHTML+="<p><b>You:</b> "+m+"<br><b>Bot:</b> "+j.reply+"</p>";
        }
        </script>
        </body></html>
        """
    # POST method (AI reply)
    data = request.get_json() or {}
    msg  = (data.get("message") or "").strip()
    user = (data.get("user") or "guest").strip()
    if not msg:
        return jsonify({"reply":"🙂 কিছু লিখুন"})
    up = msg.upper()
    reply = ""
    if "ORDER" in up:
        oid = next((t for t in up.split() if t.startswith("ORDER")), "")
        found = next((o for o in orders if o["order_id"].upper()==oid), None)
        reply = found["status"] if found else "❌ অর্ডার পাওয়া যায়নি।"
    elif "লিস্ট" in msg or "list" in msg.lower():
        items="".join([f"<li>{p['category']} — <b>{p['name']}</b> ({p['price']})</li>" for p in products])
        reply=f"<b>প্রোডাক্ট লিস্ট:</b><ul>{items}</ul>"
    else:
        found = next((p for p in products if p["name"].lower() in msg.lower()), None)
        if found:
            reply = f"{found['name']} - {found['price']} (স্টক: {found['stock']})"
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
    if not prod: return jsonify({"status":"fail","message":"Product not found"}), 404
    if prod["stock"] <= 0: return jsonify({"status":"fail","message":"স্টক নেই"}), 400
    prod["stock"] -= 1
    save_json(PRODUCTS_FILE, products)
    unit = parse_price_any(prod["price"])
    total = round(unit*(1+TAX_RATE))
    oid=f"ORDER{1000+len(orders)+1}"
    now=datetime.now().isoformat()
    rec={"order_id":oid,"user":user,"product":name,"qty":1,"unit_price":unit,"total":total,"status":"✅ Confirmed","time":now}
    orders.append(rec); save_json(ORDERS_FILE,orders)
    pdf_rel=gen_invoice(rec)
    send_email(f"New Order {oid}",f"{user} ordered {name}.")
    return jsonify({"status":"success","order_id":oid,"invoice":pdf_rel})

# ---------- Runner ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 Server running on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
