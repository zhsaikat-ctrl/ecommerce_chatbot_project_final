# -*- coding: utf-8 -*-
"""
E-commerce Chatbot — FINAL FULL VERSION
---------------------------------------
Features:
- Login (admin/staff/guest), Bootstrap 5 clean UI (no blur)
- Chatbot + Product Cards + Buy Now (stock decrement)
- Admin Orders Dashboard: list/update, invoice PDF
- Sales Reports Dashboard (today/month/year + category chart)
- Email notification (optional via .env)
- WhatsApp Cloud API webhook (/webhook/whatsapp) -> uses the same /chat logic
- Deploy-friendly env keys

Run:
    pip install flask requests reportlab python-dotenv pillow
    python server_full_final.py
"""
import os, json, re, smtplib, requests, math
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

# WhatsApp Cloud API
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
        f"Discount: {int(order.get('discount',0)*100)}%",
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
        {"category":"ল্যাপটপ","name":"Dell Inspiron 15","price":"৳65,000","stock":9,"image":"","description":"i5 • 8/512 • FHD"},
        {"category":"মোবাইল","name":"Redmi Note 13","price":"৳23,999","stock":8,"image":"","description":"6/128 • 120Hz AMOLED"},
        {"category":"অ্যাক্সেসরিজ","name":"Logitech M331 Silent","price":"৳1,799","stock":15,"image":"","description":"Silent wireless mouse"},
    ]
    save_json(PRODUCTS_FILE, products)

# ---------- HTML ----------
HTML = r"""
<!doctype html>
<html lang="bn">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>🛍️ E-commerce Chatbot — Final</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
:root{--bg:#181b22;--panel:#202531;--panel2:#23293a;--text:#e9ecf2;--muted:#aeb3c2;--accent:#19c37d;--border:#2f3445}
html,body{height:100%}
body{background:var(--bg);color:var(--text);font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Arial;
      -webkit-font-smoothing:antialiased; text-rendering:optimizeLegibility}
.card{background:var(--panel);border:1px solid var(--border);border-radius:16px}
.btn-accent{background:var(--accent);color:#fff;border:0} .btn-accent:hover{background:#0ea371}
.form-control{background:#1e2230;border:1px solid #394057;color:var(--text)}
.form-control:focus{border-color:var(--accent);box-shadow:none;outline:none}
.chat-box{height:56vh;overflow:auto;background:#1f2533;border:1px solid #32384a;border-radius:12px;padding:12px}
.msg-u{background:#0b93f6;color:#fff;border-radius:12px;padding:8px 12px;display:inline-block;max-width:80%}
.msg-b{background:#2f3446;border:1px solid #3b4158;border-radius:12px;padding:8px 12px;display:inline-block;max-width:80%}
.product-card{background:#242b3d;border:1px solid #3b4158;border-radius:12px;padding:10px;width:300px}
.product-card img{width:100%;border-radius:8px}
.badge-low{background:#4d2a2a;color:#ff9a9a}
.small-muted{color:var(--muted);font-size:12px}
</style>
</head>
<body>
<div class="container py-4">
  <h3 class="text-center mb-3">🤖 E-commerce Chatbot — Final</h3>

  <!-- Login -->
  <div id="login" class="card mx-auto" style="max-width:460px;">
    <div class="card-body">
      <h5 class="mb-3">🔐 লগইন করুন</h5>
      <input id="username" class="form-control mb-2" placeholder="admin / staff / guest">
      <input id="password" type="password" class="form-control mb-3" placeholder="password (admin/staff = 1234)">
      <div class="d-grid gap-2">
        <button class="btn btn-accent" onclick="login()">Login</button>
        <button class="btn btn-outline-light" onclick="guest()">Guest</button>
      </div>
      <div id="login-msg" class="mt-2 text-warning"></div>
    </div>
  </div>

  <!-- App -->
  <div id="app" class="d-none">
    <ul class="nav nav-tabs mb-3">
      <li class="nav-item"><button class="nav-link active" id="tab-chat" onclick="showTab('chat')">💬 Chat</button></li>
      <li class="nav-item"><button class="nav-link d-none role-staff role-admin" id="tab-admin" onclick="showTab('admin')">📦 Orders</button></li>
      <li class="nav-item"><button class="nav-link d-none role-staff role-admin" id="tab-reports" onclick="showTab('reports')">📊 Reports</button></li>
    </ul>

    <!-- Chat -->
    <div id="sec-chat" class="tab-sec">
      <div class="card mb-3">
        <div class="card-body">
          <div id="chat" class="chat-box mb-3"></div>
          <div class="input-group">
            <input id="msg" class="form-control" placeholder="লিখুন… HP / Redmi / লিস্ট / ORDER1001">
            <button class="btn btn-accent" onclick="send()">Send</button>
          </div>
          <div class="small-muted mt-2">টিপ: “লিস্ট” লিখে সব প্রোডাক্ট দেখুন। Buy Now চাপলেই অর্ডার হবে।</div>
        </div>
      </div>
      <div class="text-center"><button class="btn btn-danger btn-sm" onclick="logout()">Logout</button></div>
    </div>

    <!-- Admin Orders -->
    <div id="sec-admin" class="tab-sec d-none">
      <div class="card">
        <div class="card-header d-flex justify-content-between align-items-center">
          <b>📦 All Orders</b>
          <button class="btn btn-sm btn-outline-light" onclick="loadOrders()">Refresh</button>
        </div>
        <div class="table-responsive">
          <table class="table table-dark table-striped m-0">
            <thead>
              <tr><th>ID</th><th>User</th><th>Product</th><th>Qty</th><th>Total</th><th>Status</th><th>Time</th><th>Invoice</th><th>Action</th></tr>
            </thead>
            <tbody id="order-tbody"></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Reports -->
    <div id="sec-reports" class="tab-sec d-none">
      <div class="row g-3">
        <div class="col-12 col-lg-4">
          <div class="card"><div class="card-body text-center">
            <h6 class="mb-2">আজকের সেলস</h6>
            <div id="kpi-today" class="fs-3">৳0</div>
          </div></div>
        </div>
        <div class="col-12 col-lg-4">
          <div class="card"><div class="card-body text-center">
            <h6 class="mb-2">এই মাসের সেলস</h6>
            <div id="kpi-month" class="fs-3">৳0</div>
          </div></div>
        </div>
        <div class="col-12 col-lg-4">
          <div class="card"><div class="card-body text-center">
            <h6 class="mb-2">এই বছরের সেলস</h6>
            <div id="kpi-year" class="fs-3">৳0</div>
          </div></div>
        </div>
        <div class="col-12">
          <div class="card"><div class="card-header">ক্যাটাগরি অনুসারে অর্ডার</div>
            <div class="card-body"><canvas id="chartCat" height="140"></canvas></div>
          </div>
        </div>
      </div>
      <div class="text-center mt-3">
        <button class="btn btn-outline-light" onclick="loadReports()">Refresh</button>
      </div>
    </div>

  </div>
</div>

<script>
let ROLE=null, USER=null, chartCat=null;

function $(id){return document.getElementById(id);}
function show(el){el.classList.remove('d-none');}
function hide(el){el.classList.add('d-none');}
function showTab(t){
  document.querySelectorAll('.tab-sec').forEach(x=>x.classList.add('d-none'));
  document.querySelectorAll('.nav-link').forEach(x=>x.classList.remove('active'));
  if(t==='chat'){show($('sec-chat'));$('tab-chat').classList.add('active');}
  if(t==='admin'){show($('sec-admin'));$('tab-admin').classList.add('active');loadOrders();}
  if(t==='reports'){show($('sec-reports'));$('tab-reports').classList.add('active');loadReports();}
}

async function login(){
  const u=$('username').value.trim(), p=$('password').value.trim();
  const out=$('login-msg'); out.textContent="";
  try{
    const r=await fetch('/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,password:p})});
    const d=await r.json();
    if(d.status==='success'){
      ROLE=d.role; USER=u||'guest';
      hide($('login')); show($('app')); $('msg').focus();
      if(ROLE==='admin'||ROLE==='staff'){ document.getElementById('tab-admin').classList.remove('d-none'); document.getElementById('tab-reports').classList.remove('d-none');}
      appendB('স্বাগতম '+USER+'! এখন আপনি চ্যাট করতে পারেন।');
    }else out.textContent=d.message||'❌ ভুল ইউজারনেম বা পাসওয়ার্ড!';
  }catch(e){ out.textContent='⚠️ লগইন করতে সমস্যা হয়েছে!'; console.error(e); }
}
function guest(){ $('username').value='guest'; $('password').value='guest'; login(); }
function logout(){ ROLE=null; USER=null; hide($('app')); show($('login')); }
function appendU(t){$('chat').insertAdjacentHTML('beforeend',`<div class="text-end mb-2"><span class="msg-u">${t}</span></div>`);$('chat').scrollTop=$('chat').scrollHeight;}
function appendB(t){$('chat').insertAdjacentHTML('beforeend',`<div class="text-start mb-2"><span class="msg-b">${t}</span></div>`);$('chat').scrollTop=$('chat').scrollHeight;}
$('msg').addEventListener('keydown',e=>{ if(e.key==='Enter') send(); });

async function send(){
  const t=$('msg').value.trim(); if(!t) return; $('msg').value=''; appendU(t);
  const r=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:t,user:USER||'guest'})});
  const d=await r.json(); appendB(d.reply);
}

/* GLOBAL: Buy Now handler */
async function placeOrder(productName){
  try{
    const r=await fetch('/add_order',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({product_name:productName,user:USER||'guest'})});
    const d=await r.json();
    if(d.status==='success'){
      alert('🛒 অর্ডার কনফার্ম!\\nআইডি: '+d.order_id);
      if(d.invoice) window.open('/'+d.invoice,'_blank');
      // refresh if admin tab open
      if(!document.getElementById('sec-admin').classList.contains('d-none')) loadOrders();
    }else alert('⚠️ '+(d.message||'অর্ডার ব্যর্থ'));
  }catch(e){ alert('⚠️ সার্ভারে সংযোগ ব্যর্থ!'); console.error(e); }
}

/* Admin: load & update orders */
async function loadOrders(){
  const list = await (await fetch('/orders')).json();
  const tb = $('order-tbody'); tb.innerHTML='';
  if(!list.length){ tb.innerHTML = '<tr><td colspan="9" class="text-center text-muted">No orders yet</td></tr>'; return; }
  for(const o of list.slice().reverse()){
    tb.insertAdjacentHTML('beforeend', `
      <tr>
        <td>${o.order_id}</td>
        <td>${o.user||'-'}</td>
        <td>${o.product}</td>
        <td>${o.qty||1}</td>
        <td>৳${o.total}</td>
        <td>${o.status}</td>
        <td>${(o.created_at||o.time||'').replace('T',' ')}</td>
        <td>${o.order_id ? `<a class="btn btn-sm btn-outline-light" href="/invoices/${o.order_id}.pdf" target="_blank">PDF</a>` : '-'}</td>
        <td class="d-flex gap-1">
          <button class="btn btn-sm btn-success" onclick="updateStatus('${o.order_id}','✅ Delivered')">Deliver</button>
          <button class="btn btn-sm btn-danger" onclick="updateStatus('${o.order_id}','❌ Cancelled')">Cancel</button>
        </td>
      </tr>
    `);
  }
}
async function updateStatus(order_id, status){
  const r=await fetch('/update_order',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({order_id, status})});
  const d=await r.json(); if(d.status==='success') loadOrders(); else alert('Update failed');
}

/* Reports */
async function loadReports(){
  const d = await (await fetch('/reports')).json();
  document.getElementById('kpi-today').textContent = '৳'+d.today;
  document.getElementById('kpi-month').textContent = '৳'+d.month;
  document.getElementById('kpi-year').textContent  = '৳'+d.year;

  if(chartCat) chartCat.destroy();
  chartCat = new Chart(document.getElementById('chartCat'), {
    type:'bar',
    data:{labels:d.categories.labels, datasets:[{label:'Orders', data:d.categories.counts}]},
    options:{plugins:{legend:{display:false}}}
  });
}
</script>
</body>
</html>
"""

# ---------- Routes ----------
@app.route("/")
def home():
    return render_template_string(HTML)

@app.route("/invoices/<path:filename>")
def serve_invoice(filename):
    return send_from_directory(INVOICES_DIR, filename)

# ---- Auth ----
@app.route("/login", methods=["POST"])
def login():
    d = request.get_json() or {}
    u = (d.get("username") or "").strip().lower()
    p = (d.get("password") or "")
    if u == "admin" and p == "1234":
        return jsonify({"status":"success","role":"admin"})
    if u == "staff" and p == "1234":
        return jsonify({"status":"success","role":"staff"})
    if u:
        return jsonify({"status":"success","role":"guest"})
    return jsonify({"status":"fail","message":"❌ Invalid login"})

# ---- API: lists ----
@app.route("/orders")
def orders_list():
    return jsonify(orders)

@app.route("/products")
def products_list():
    return jsonify(products)

# ---- Chat ----
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json() or {}
    msg  = (data.get("message") or "").strip()
    user = (data.get("user") or "guest").strip()
    reply = ""

    if not msg:
        return jsonify({"reply":"🙂 কিছু লিখুন"})

    up = msg.upper()

    if "ORDER" in up:
        tokens = up.split()
        oid = next((t for t in tokens if t.startswith("ORDER")), None)
        found = next((o for o in orders if o["order_id"].upper()==(oid or "").upper()), None)
        reply = found["status"] if found else "❌ এই অর্ডার আইডি পাওয়া যায়নি।"

    elif ("লিস্ট" in msg) or ("list" in msg.lower()) or ("কি কি" in msg):
        items="".join([f"<li>{p['category']} — <b>{p['name']}</b> ({p['price']}, স্টক: {p['stock']})</li>" for p in products])
        reply=f"<b>আমাদের প্রোডাক্ট লিস্ট:</b><ul class='m-0'>{items or '<li>ফাঁকা</li>'}</ul>"

    else:
        found = next((p for p in products if p["name"].lower() in msg.lower() or p["category"].lower() in msg.lower()), None)
        if found:
            stock=int(found.get("stock") or 0)
            low = " <span class='badge badge-low ms-1'>Low</span>" if stock <= LOW_STOCK else ""
            img = f"<img src='/{found['image']}' class='mb-2' alt='{found['name']}'>" if found.get("image") else ""
            reply=(f"<div class='product-card'>{img}<b>{found['name']}</b>{low}<br>"
                   f"💰 {found['price']} — 📦 {stock} স্টক<br>"
                   f"<button class='btn btn-sm btn-accent mt-1' onclick=\"placeOrder('{found['name']}')\">🛒 Buy Now</button></div>")
        else:
            try:
                rr = requests.post(OLLAMA_URL, json={"model": OLLAMA_MODEL, "prompt": msg, "stream": False}, timeout=7)
                reply = rr.json().get("response","🤖 আমি সাহায্য করতে প্রস্তুত! প্রোডাক্টের নাম বলুন।")
            except Exception:
                reply = "🤖 আমি সাহায্য করতে প্রস্তুত! প্রোডাক্টের নাম বলুন।"

    history.append({"time": datetime.now().isoformat(timespec="seconds"), "user": user, "msg": msg, "bot": reply})
    history[:] = history[-400:]
    save_json(HISTORY_FILE, history)
    return jsonify({"reply": reply})

# ---- Orders (create/update) ----
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
        "unit_price": unit, "discount": 0, "tax": TAX_RATE, "total": total,
        "status": "✅ Confirmed", "created_at": now, "time": now,
        "category": prod.get("category","Unknown")
    }
    orders.append(rec); save_json(ORDERS_FILE, orders)
    pdf_rel = gen_invoice(rec)
    send_email(f"New Order {oid}", f"{user} ordered {name}. Total: {total}")
    return jsonify({"status":"success","order_id": oid, "invoice": pdf_rel})

@app.route("/update_order", methods=["POST"])
def update_order():
    d = request.get_json() or {}
    oid = (d.get("order_id") or "").strip()
    st  = (d.get("status") or "").strip()
    for o in orders:
        if o["order_id"] == oid:
            o["status"] = st
            save_json(ORDERS_FILE, orders)
            return jsonify({"status":"success"})
    return jsonify({"status":"fail","message":"Not found"}), 404

# ---- Reports API ----
@app.route("/reports")
def reports():
    # KPIs
    today_s = 0; month_s = 0; year_s = 0
    cat_count = {}
    today_str = date.today().isoformat()
    m_prefix  = today_str[:7]   # YYYY-MM
    y_prefix  = today_str[:4]   # YYYY

    for o in orders:
        total = int(o.get("total",0))
        t = (o.get("created_at") or o.get("time") or "")
        if t.startswith(today_str): today_s += total
        if t.startswith(m_prefix):  month_s += total
        if t.startswith(y_prefix):  year_s  += total
        cat = o.get("category","Unknown")
        cat_count[cat] = cat_count.get(cat, 0) + 1

    labels = list(cat_count.keys())
    counts = [cat_count[k] for k in labels]

    return jsonify({
        "today": today_s,
        "month": month_s,
        "year":  year_s,
        "categories": {"labels": labels, "counts": counts}
    })

# ---- WhatsApp Webhook ----
@app.route("/webhook/whatsapp", methods=["GET","POST"])
def wa_webhook():
    # Verification (GET)
    if request.method == "GET":
        mode  = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        chal  = request.args.get("hub.challenge")
        if mode == "subscribe" and token == WA_VERIFY:
            return chal, 200
        return "forbidden", 403

    # Messages (POST)
    data = request.get_json() or {}
    try:
        # Extract message text & sender
        entry = data["entry"][0]["changes"][0]["value"]
        if "messages" not in entry: return "ok"
        msg = entry["messages"][0]
        from_wa = msg["from"]   # phone number
        text = ""
        if msg["type"] == "text":
            text = msg["text"]["body"]
        else:
            text = "(unsupported message type)"

        # Call internal /chat logic
        r = app.test_client().post("/chat", json={"message": text, "user": f"whatsapp:{from_wa}"})
        bot = r.get_json().get("reply","")

        # Strip HTML tags for WhatsApp
        reply_text = re.sub(r"<[^>]+>", " ", bot)
        reply_text = re.sub(r"\s+", " ", reply_text).strip()
        if not reply_text:
            reply_text = "🤖 আমি সাহায্য করতে প্রস্তুত! প্রোডাক্টের নাম বলুন।"

        # Send back via Cloud API
        if WA_TOKEN and WA_PHONE_ID:
            url = f"https://graph.facebook.com/v19.0/{WA_PHONE_ID}/messages"
            headers = {"Authorization": f"Bearer {WA_TOKEN}", "Content-Type": "application/json"}
            payload = {
                "messaging_product": "whatsapp",
                "to": from_wa,
                "type": "text",
                "text": {"body": reply_text}
            }
            requests.post(url, headers=headers, json=payload, timeout=10)

    except Exception as e:
        print("WA webhook error:", e)

    return "ok", 200

# ---------- Main ----------
if __name__=="__main__":
    if not os.path.exists(PRODUCTS_FILE): save_json(PRODUCTS_FILE, products)
    if not os.path.exists(ORDERS_FILE):   save_json(ORDERS_FILE,   [])
    if not os.path.exists(HISTORY_FILE):  save_json(HISTORY_FILE,  [])
    print("🚀 Running on http://127.0.0.1:5000/")
    app.run(debug=True)
