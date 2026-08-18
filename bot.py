"""
MULTIAPI USERBOT — Group 1 & Group 2 only
- /multiapi endpoint (Bot 1 / MultiAPI system)
- API key system (limits, expiry, usage)
- Everything else (Truecaller bot, user lookup, DZHQ bypass, admin panel) removed

CONFIG: apni values env vars ya niche placeholders me daalein.
"""

from flask import Flask, request, jsonify
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.network.connection.tcpabridged import ConnectionTcpAbridged
from telethon.tl.types import MessageEntityPre, MessageEntityCode
from telethon.errors import AuthKeyError
import asyncio
import threading
import re
import json
import logging
import os
import secrets
from datetime import datetime

# ==================== PORT ====================
PORT = int(os.environ.get("PORT", 10000))

# ==================== CREDENTIALS (apni values daalein) ====================
API_ID = int(os.environ.get("API_ID", "29308061"))              # e.g. 1234567
API_HASH = os.environ.get("API_HASH", "462de3dfc98fd938ef9c6ee31a72d099")
STRING_SESSION = os.environ.get("STRING_SESSION", "1BVtsOHwBu222s9ND_lgKFjg3PYUbr_tccXz3zDTTHIsMcag2x6Yo1jpNxmeJLWT6kuoqCQ3cMw_hxW3P128xwNmUWDBBVaW2CMq8z4Pt-qd2cGv3JprnHFpw3ojuh51LsbFzWouI487xaslYe5joIKE3kV34dT3ppJtuD9OyyuIXzEVBHBlC1cl2zs-eu2NH3G3urp6VAxrSwQ7kpa34ex9yfT_GKIY34cxdMGvGw5_a1Fbdv-q6jjvndztcuorYbVfbFvcnnA-qfiMJagBxz8qoY2eX9MJvTsWsD1UY99BPcpIscc2_iGJoxK1bXh5x5PXxGOOOxaPrDELn1witmTQF9MZHj84=")
API_KEY = os.environ.get("API_KEY", "SAHIL")

# ==================== GROUPS (apne group link / id daalein) ====================
# GROUP1 -> username/link ya numeric id | GROUP2 -> numeric id ya link
GROUP1 = os.environ.get("GROUP1", "https://t.me/iicxzz")        # e.g. "https://t.me/yourgroup"
_g2 = os.environ.get("GROUP2", "-1003850536279")           # e.g. "-1001234567890"
GROUP2 = int(_g2) if str(_g2).lstrip("-").isdigit() else _g2

AUTO_DELETE_SECONDS = 5

# ==================== BRANDING ====================
DEVELOPER = os.environ.get("DEVELOPER", "@sahilxalone")
CHANNEL = os.environ.get("CHANNEL", "")
# Upstream bot ka username jo response me aata hai -> apne username se replace
SOURCE_USERNAME = os.environ.get("SOURCE_USERNAME", "UsersXinfo_admin")
MY_USERNAME = os.environ.get("MY_USERNAME", DEVELOPER.lstrip("@"))

# ==================== STORAGE ====================
GENERATED_KEYS = {}
TELEGRAM_ACCOUNTS = {}
DAILY_USAGE = {}
pending = {}
counter = 0
stats = {"total": 0, "success": 0, "failed": 0}
loop = None
client = None

logging.basicConfig(level=logging.WARNING)
logging.getLogger('telethon').setLevel(logging.WARNING)

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

# ==================== ACCOUNT MANAGER ====================
class AccountManager:
    def __init__(self):
        self._clients = {}
        self._rr_index = 0
        self._lock = threading.Lock()

    def get_active_ids(self):
        return [aid for aid, acc in TELEGRAM_ACCOUNTS.items() if acc.get('active', True)]

    def get_client(self, acc_id):
        return self._clients.get(acc_id)

    def set_client(self, acc_id, client):
        self._clients[acc_id] = client

    def remove_client(self, acc_id):
        return self._clients.pop(acc_id, None)

    def get_any_client(self):
        for aid in self.get_active_ids():
            cl = self._clients.get(aid)
            if cl and cl.is_connected():
                return cl
        return None

    def next_client(self):
        with self._lock:
            active_ids = [
                aid for aid in self.get_active_ids()
                if aid in self._clients and self._clients[aid].is_connected()
            ]
            if not active_ids:
                return None, None
            idx = self._rr_index % len(active_ids)
            self._rr_index = (self._rr_index + 1) % len(active_ids)
            aid = active_ids[idx]
            return aid, self._clients[aid]

acc_manager = AccountManager()

TELEGRAM_ACCOUNTS["default"] = {
    "id": "default",
    "name": "Main Account",
    "api_id": API_ID,
    "api_hash": API_HASH,
    "session_string": STRING_SESSION,
    "active": True,
    "created_at": datetime.now().isoformat()
}
# ==================== COMMANDS ====================
COMMANDS = {
    "num": GROUP1, "vnum": GROUP1, "veh": GROUP1, "insta": GROUP1,
    "ip": GROUP1, "email": GROUP1, "ifsc": GROUP1, "adhar": GROUP1,
    "imei": GROUP1, "pak": GROUP1, "gst": GROUP1, "bomber": GROUP1,
    "upiinfo": GROUP2, "fam": GROUP2, "tg": GROUP2, "pan": GROUP2,
    "leak": GROUP2, "family": GROUP2,
}
# ==================== UTILITIES ====================
# ==================== UTILITIES ====================
def clean_num(n):
    s = str(n).strip()
    digits = re.sub(r'[^\d]', '', s)
    if digits:
        if len(digits) == 12 and digits[:2] in ('91', '92'):
            candidate = digits[2:]
            if len(candidate) >= 8:
                digits = candidate
        return digits
    return s

def replace_username_in_json(data):
    """Upstream bot ke username ko apne username se replace karta hai."""
    def fix(s):
        if SOURCE_USERNAME and SOURCE_USERNAME in s:
            return s.replace("@" + SOURCE_USERNAME, "@" + MY_USERNAME).replace(SOURCE_USERNAME, MY_USERNAME)
        return s
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, str):
                data[key] = fix(value)
            elif isinstance(value, (dict, list)):
                replace_username_in_json(value)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            if isinstance(item, str):
                data[i] = fix(item)
            elif isinstance(item, (dict, list)):
                replace_username_in_json(item)
    return data

# ==================== VALIDATE KEY ====================
KEY_MESSAGES = {
    "expired": ("expired", "API Key Expired",
                "Your API key is no longer valid. Please buy a new key to continue."),
    "revoked": ("expired", "API Key Revoked",
                "Your API key is no longer valid. Please buy a new key to continue."),
    "limit_total": ("expired", "API Key Limit Reached",
                    "Your API key is no longer valid. Please buy a new key to continue."),
    "limit_daily": ("limit", "Daily Limit Reached",
                    "You have used all requests allowed for today. Try again tomorrow or buy a bigger plan."),
    "invalid": ("invalid", "Invalid API Key",
                "Your API key is no longer valid. Please buy a new key to continue."),
}


def key_error_response(reason):
    """Uniform error body for every endpoint when a key is not usable."""
    status, message, error = KEY_MESSAGES.get(reason or "invalid", KEY_MESSAGES["invalid"])
    return jsonify({
        "status": status,
        "message": message,
        "error": error,
        "developer": DEVELOPER,
        "channel": CHANNEL
    }), 401


def _today_str():
    return datetime.now().strftime("%Y-%m-%d")


def _roll_day(data):
    """Reset daily counter when the date changed."""
    today = _today_str()
    if data.get("day") != today:
        data["day"] = today
        data["used_today"] = 0


def key_public_view(k, data):
    _roll_day(data)
    expiry = data.get("expiry")
    days_left = None
    is_expired = False
    if expiry:
        try:
            delta = datetime.fromisoformat(expiry) - datetime.now()
            days_left = max(0, delta.days)
            is_expired = delta.total_seconds() <= 0
        except Exception:
            pass
    total_limit = int(data.get("total_limit") or 0)
    daily_limit = int(data.get("daily_limit") or 0)
    total_used = int(data.get("total_used") or 0)
    used_today = int(data.get("used_today") or 0)
    if total_limit and total_used >= total_limit:
        is_expired = True
    expires_on = None
    if expiry:
        try:
            expires_on = datetime.fromisoformat(expiry).strftime("%Y-%m-%d")
        except Exception:
            expires_on = None
    return {
        "key": k,
        "name": data.get("name", ""),
        "expires_on": expires_on,
        "valid_days": days_left if days_left is not None else 9999,
        "active": data.get("active", True),
        "expiry": expiry,
        "days_left": days_left,
        "daily_limit": daily_limit,
        "total_limit": total_limit,
        "used_today": used_today,
        "total_used": total_used,
        "remaining_today": (daily_limit - used_today) if daily_limit else None,
        "remaining_total": (total_limit - total_used) if total_limit else None,
        "expired": is_expired,
        "created_at": data.get("created_at"),
        "last_used": data.get("last_used"),
        "note": data.get("note", ""),
    }


def key_details_view(api_key):
    """Public key_details block returned with every successful API response."""
    data = GENERATED_KEYS.get(api_key)
    if not data:
        # Permanent/master key -> clean JSON, no key_details block at all
        return None
    _roll_day(data)
    expires_on, valid_days = None, 9999
    expiry = data.get("expiry")
    if expiry:
        try:
            dt = datetime.fromisoformat(expiry)
            expires_on = dt.strftime("%Y-%m-%d")
            valid_days = max(0, (dt - datetime.now()).days)
        except Exception:
            pass
    return {
        "daily_limit": int(data.get("daily_limit") or 0),
        "expires_on": expires_on,
        "used_today": int(data.get("used_today") or 0),
        "valid_days": valid_days,
    }


def validate_api_key(api_key, count_usage=True):
    """Returns (ok, reason). reason -> expired / revoked / limit_total / limit_daily / invalid"""
    if api_key == API_KEY:
        return True, None
    data = GENERATED_KEYS.get(api_key)
    if not data:
        return False, "invalid"

    if not data.get('active', True):
        return False, ("limit_total" if data.get('exhausted') else "revoked")

    if data.get('expiry'):
        try:
            if datetime.now() > datetime.fromisoformat(data['expiry']):
                return False, "expired"
        except Exception:
            pass

    _roll_day(data)

    total_limit = int(data.get('total_limit') or 0)
    if total_limit and int(data.get('total_used') or 0) >= total_limit:
        data['active'] = False
        data['exhausted'] = True
        return False, "limit_total"

    daily_limit = int(data.get('daily_limit') or 0)
    if daily_limit and int(data.get('used_today') or 0) >= daily_limit:
        return False, "limit_daily"

    if count_usage:
        data['total_used'] = int(data.get('total_used') or 0) + 1
        data['used_today'] = int(data.get('used_today') or 0) + 1
        data['last_used'] = datetime.now().isoformat()
        DAILY_USAGE[_today_str()] = DAILY_USAGE.get(_today_str(), 0) + 1
        if total_limit and data['total_used'] >= total_limit:
            data['active'] = False
            data['exhausted'] = True
    return True, None
# ==================== BOT 1 HELPERS ====================
def safe_json_loads(text):
    try:
        return json.loads(text)
    except:
        return None

def extract_json(text):
    if not text:
        return None
    stack = []
    start = -1
    for i, ch in enumerate(text):
        if ch == '{':
            if not stack:
                start = i
            stack.append('{')
        elif ch == '}':
            if stack:
                stack.pop()
                if not stack and start != -1:
                    result = safe_json_loads(text[start:i + 1])
                    if result is not None:
                        return result
    return None

def get_code_block(msg):
    if not msg or not msg.entities or not msg.text:
        return None
    text = msg.text
    for entity in msg.entities:
        if not isinstance(entity, (MessageEntityPre, MessageEntityCode)):
            continue
        offset = entity.offset
        length = entity.length
        try:
            from telethon.utils import add_surrogate, del_surrogate
            surr = add_surrogate(text)
            content = del_surrogate(surr[offset:offset + length])
            if content.strip():
                return content
        except:
            pass
        try:
            content = text[offset:offset + length]
            if content.strip():
                return content
        except:
            pass
    return None

def get_part_info(text):
    match = re.search(r'[Pp]art\s+(\d+)/(\d+)', text)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None, None

def is_info_bot(sender):
    if not sender:
        return False
    username = str(getattr(sender, 'username', '') or '').lower()
    return 'usersxinfo' in username

async def delete_msg(chat_id, msg_id, delay=5):
    await asyncio.sleep(delay)
    try:
        cl = acc_manager.get_any_client()
        if cl and cl.is_connected():
            await cl.delete_messages(chat_id, msg_id)
    except:
        pass
# ==================== BOT 1 SEND ====================
async def send_cmd(cmd, val, timeout=25):
    if cmd not in COMMANDS:
        return {"success": False, "error": "Unknown command: " + cmd}

    _, use_client = acc_manager.next_client()
    if not use_client or not use_client.is_connected():
        return {"success": False, "error": "No Telegram client connected"}

    target = COMMANDS[cmd]
    global counter
    counter += 1
    rid = str(counter)
    done_event = asyncio.Event()
    pending[rid] = {
        "cmd": cmd, "val": val, "event": done_event,
        "json_data": None, "done": False,
        "parts": {}, "part_msgs": {}, "total_parts": None,
    }
    try:
        sent = await use_client.send_message(target, "/" + cmd + " " + val)
        print("[SENT] /" + cmd + " " + val)
        asyncio.create_task(delete_msg(target, sent.id))
        try:
            await asyncio.wait_for(done_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass
        result_json = pending[rid].get("json_data")
        if not result_json:
            return {"success": False, "error": "No JSON received"}
        result_json = replace_username_in_json(result_json)
        return {
            "success": True, "command": cmd, "value": val,
            "timestamp": datetime.now().isoformat(),
            "result": result_json, "stats": stats,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        pending.pop(rid, None)
# ==================== BOT 1 HANDLER ====================
@events.register(events.NewMessage)
async def on_message_bot1(event):
    msg = event.message
    if not msg or not msg.text:
        return
    sender = await event.get_sender()
    if not is_info_bot(sender):
        return
    text = msg.text
    current_part, total_parts = get_part_info(text)
    if current_part is not None and total_parts is not None and total_parts > 1:
        matched_rid = None
        matched_req = None
        for rid, req in list(pending.items()):
            if req.get("done"):
                continue
            if req["val"] in text and current_part not in req["parts"]:
                matched_rid = rid
                matched_req = req
                break
        if matched_rid is None:
            for rid, req in list(pending.items()):
                if req.get("done"):
                    continue
                if req.get("total_parts") == total_parts:
                    if current_part not in req["parts"]:
                        matched_rid = rid
                        matched_req = req
                        break
        if matched_rid is None:
            return
        matched_req["parts"][current_part] = text
        matched_req["part_msgs"][current_part] = msg
        matched_req["total_parts"] = total_parts
        print("[PART] " + str(current_part) + "/" + str(total_parts) + " for " + matched_rid)
        if len(matched_req["parts"]) == total_parts:
            _complete_multipart(matched_rid, matched_req)
    else:
        for rid, req in list(pending.items()):
            if req.get("done"):
                continue
            if req["val"] not in text:
                continue
            code = get_code_block(msg)
            data = extract_json(code) if code else None
            if not data:
                data = extract_json(text)
            if data:
                data = replace_username_in_json(data)
                req["json_data"] = data
                req["done"] = True
                req["event"].set()
                print("[OK] Single msg JSON for " + rid)
            else:
                req["event"].set()
                print("[FAIL] No JSON single msg for " + rid)
            break

def _complete_multipart(rid, req):
    sorted_parts = sorted(req["parts"])
    fragments = []
    for part_num in sorted_parts:
        msg_obj = req["part_msgs"].get(part_num)
        raw_text = req["parts"].get(part_num, "")
        code = get_code_block(msg_obj) if msg_obj else None
        if code and code.strip():
            bt = code.find('```')
            if bt != -1:
                frag = code[bt + 3:]
            else:
                idx = code.find('{')
                if idx != -1:
                    frag = code[idx:]
                else:
                    frag = code
        else:
            bt = raw_text.find('```')
            if bt != -1:
                frag = raw_text[bt + 3:]
            else:
                m = re.search(r'\bJSON\s*\n', raw_text, re.IGNORECASE)
                if m:
                    frag = raw_text[m.end():]
                else:
                    idx = raw_text.find('{')
                    if idx != -1:
                        frag = raw_text[idx:]
                    else:
                        frag = raw_text.strip()
        fragments.append(frag)
    combined_s1 = "".join(fragments)
    data = safe_json_loads(combined_s1.strip())
    if not data:
        data = extract_json(combined_s1)
    if not data:
        raw_all = "".join(req["parts"][i] for i in sorted_parts)
        stack = []
        start = -1
        for i, ch in enumerate(raw_all):
            if ch == '{':
                if not stack:
                    start = i
                stack.append('{')
            elif ch == '}' and stack:
                stack.pop()
                if not stack and start != -1:
                    candidate = raw_all[start:i + 1]
                    data = safe_json_loads(candidate)
                    if not data:
                        filtered = '\n'.join([
                            line for line in candidate.split('\n')
                            if not (len(set(line.strip())) == 1 and len(line.strip()) >= 5) and
                            not re.search(r'TARGET\s*:|REPORT\s*:|AGENT\s*:|This message|Please copy|Part\s+\d+/\d+|SCROLL|USE ME|Add Me|Next part|automatically|before it disappears', line, re.IGNORECASE)
                        ]).replace('`', '')
                        data = safe_json_loads(filtered)
                    if data:
                        break
                    stack = []
                    start = -1
    if data:
        data = replace_username_in_json(data)
        req["json_data"] = data
    req["done"] = True
    req["event"].set()
# ==================== ROUTES ====================
@app.route('/multiapi', methods=['GET'])
def multi_api():
    key = request.args.get('key', '')
    valid, error = validate_api_key(key)
    if not valid:
        return key_error_response(error)
    
    cmd = None
    val = None
    for c in COMMANDS.keys():
        v = request.args.get(c, '')
        if v:
            cmd = c
            val = v
            break
    
    if not cmd:
        return jsonify({
            "success": False, 
            "error": "Missing command",
            "available_commands": list(COMMANDS.keys())
        }), 400
    
    stats["total"] += 1
    try:
        future = asyncio.run_coroutine_threadsafe(send_cmd(cmd, val), loop)
        result = future.result(timeout=25)
    except Exception as e:
        stats["failed"] += 1
        return jsonify({"success": False, "error": str(e), "stats": stats}), 500
    
    if result.get("success"):
        stats["success"] += 1
        return jsonify({
            "success": True,
            "command": cmd,
            "value": val,
            "timestamp": datetime.now().isoformat(),
            "result": result.get("result"),
            "stats": stats,
        })
    else:
        stats["failed"] += 1
        return jsonify({"success": False, "error": result.get("error"), "stats": stats}), 500


@app.route('/')
def home():
    return jsonify({
        "status": "success",
        "title": "API Store",
        "availability": "All APIs Available",
        "action": "DM to Buy",
        "contact": DEVELOPER
    })


@app.route('/health')
def health():
    active_ids = [aid for aid, a in TELEGRAM_ACCOUNTS.items() if a.get('active', True)]
    connected = sum(1 for aid in active_ids
                    if acc_manager.get_client(aid) and acc_manager.get_client(aid).is_connected())
    return jsonify({
        "status": "ok",
        "stats": stats,
        "accounts": len(active_ids),
        "connected": connected,
        "pending": len(pending)
    })


# ============ UNIFIED PUBLIC API RESPONSE FORMAT ============
WRAPPED_PATHS = {'/multiapi'}
STRIP_FIELDS = ('stats', 'timestamp', 'value', 'bot1_stats', 'bot2_stats')
# Fields that some upstream group bots inject into their own JSON. We remove
# them from the inner `result` so only OUR outer key_details / developer
# survive in the final response.
INNER_STRIP_FIELDS = (
    'key_details', 'developer', 'channel',
    'success', 'status_code', 'http_status',
    'api_owner', 'owner', 'bot_owner',
)


def _deep_strip_inner(obj):
    if isinstance(obj, dict):
        for f in INNER_STRIP_FIELDS:
            obj.pop(f, None)
        for v in obj.values():
            _deep_strip_inner(v)
    elif isinstance(obj, list):
        for v in obj:
            _deep_strip_inner(v)


@app.after_request
def unified_response_format(resp):
    """Removes stats/timestamp/value and attaches developer + key_details."""
    try:
        path = request.path.rstrip('/') or '/'
        if path not in WRAPPED_PATHS:
            return resp
        if 'application/json' not in (resp.content_type or ''):
            return resp
        body = resp.get_json(silent=True)
        if not isinstance(body, dict):
            return resp
        for f in STRIP_FIELDS:
            body.pop(f, None)
        if isinstance(body.get('result'), dict):
            for f in STRIP_FIELDS:
                body['result'].pop(f, None)
            # Strip the upstream bot's key_details / developer / success flags
            # so ONLY our outer key_details block is shown.
            _deep_strip_inner(body['result'])
        body['developer'] = DEVELOPER
        body['http_status'] = resp.status_code
        body['status_code'] = resp.status_code
        if 'success' not in body:
            body['success'] = resp.status_code == 200
        details = key_details_view(request.args.get('key', ''))
        body.pop('key_details', None)
        if details:
            body['key_details'] = details
        resp.set_data(json.dumps(body, indent=2, default=str))
        resp.headers['Content-Type'] = 'application/json'
    except Exception as e:
        print("[RESPONSE FORMAT ERROR]", e)
    return resp


# ==================== MAIN ====================
async def main():
    global loop, client
    loop = asyncio.get_running_loop()
    try:
        client = TelegramClient(
            StringSession(STRING_SESSION),
            API_ID,
            API_HASH,
            connection=ConnectionTcpAbridged,
            auto_reconnect=True,
            receive_updates=True
        )
        await client.start()
        client.add_event_handler(on_message_bot1)
        acc_manager.set_client("default", client)

        me = await client.get_me()
        print("=" * 55)
        print("MULTIAPI USERBOT — Group 1 & Group 2")
        print(f"Logged in as: {me.first_name} (@{me.username})")
        print("=" * 55)
        print("   /multiapi?key=YOUR_KEY&num=NUMBER")
        print("   /multiapi?key=YOUR_KEY&adhar=NUMBER")
        print("   Commands: " + ", ".join(COMMANDS.keys()))
        print("=" * 55)

        await client.run_until_disconnected()

    except AuthKeyError:
        print("Session expired! Naya STRING_SESSION daalein.")
        while True:
            await asyncio.sleep(60)
    except Exception as e:
        print(f"Error: {e}")
        await asyncio.sleep(5)


def run_flask():
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(main())
