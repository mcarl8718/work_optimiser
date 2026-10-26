#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re, json, html, time, urllib.request, urllib.error
from pathlib import Path
import os

BOT_TOKEN   = os.environ["BOT_TOKEN"].strip()
MY_USER_ID  = re.sub(r'\D', '', os.environ["MY_USER_ID"]) 
AI_API  = os.environ["AI_API"].strip()
print(f"DEBUG ID LENGTH: {len(MY_USER_ID)}")

CHANNELS = [
    "castingsmodels", "he1pers", "workermoscowstudents",
    "manmodels", "MVModelVision", "castingovnet"
]

USER_INTERESTS = """
одобряй только для мужчин, со ставкой только выше 499 рублей в час. если ставка не указана - одобряй. если сложное решение - одобряй. Всегда лучше одобрить, чем отказать, если отказ не очевидно верен
"""


AI_BASE_URL = "https://api.groq.com/openai/v1"
AI_MODEL    = "openai/gpt-oss-120b"

STATE_FILE = Path(__file__).parent / "state.json"

AI_YES, AI_NO, AI_FAIL = "yes", "no", "fail"


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def post_json(url, payload, headers=None, timeout=25):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def get(url, timeout=25):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) Chrome/120.0")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text("utf-8"))
        except Exception:
            return {}
    return {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), "utf-8")


# ─── Отправка сообщений ──────────────────────────────────────

def send_text(chat_id, text):
    payload = {"chat_id": chat_id, "text": text,
               "disable_web_page_preview": True}
    try:
        post_json(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", payload)
        return True
    except urllib.error.HTTPError as e:
        log(f"  TG HTTP {e.code}: {e.read().decode('utf-8','replace')[:200]}")
    except Exception as e:
        log(f"  TG ошибка: {e}")
    return False


def send(channel, text, link, note=None):
    header = f"📌 @{channel}" if not note else f"{note}\n📌 @{channel}"
    payload = {
        "chat_id": MY_USER_ID,
        "text": f"{header}\n\n{text}\n\n🔗 {link}",
        "disable_web_page_preview": False,
    }
    try:
        post_json(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", payload)
        return True
    except urllib.error.HTTPError as e:
        log(f"  TG HTTP {e.code}: {e.read().decode('utf-8','replace')[:200]}")
    except Exception as e:
        log(f"  TG ошибка: {e}")
    return False


# ─── Приём команд от владельца ───────────────────────────────

def extract_channel(s):
    """Достаёт username канала из 'https://t.me/xxx', '@xxx' или 'xxx'."""
    s = s.strip().rstrip("/")
    m = re.match(r"(?:https?://)?t\.me/([A-Za-z0-9_]+)", s)
    if m:
        return m.group(1)
    m = re.match(r"@?([A-Za-z0-9_]{4,32})$", s)
    if m:
        return m.group(1)
    return None


def handle_updates(state):
    """Опрашивает бота, обрабатывает команды. Возвращает set новых каналов."""
    last_uid = state.get("_last_update_id", 0)
    channels = set(state.get("_channels", []))

    try:
        resp = json.loads(get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
            f"?offset={last_uid + 1}&timeout=0"
        ))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:200]
        log(f"getUpdates HTTP {e.code}: {body}")
        if e.code == 409:
            log("⚠️ На боте стоит вебхук. Убери его: "
                f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")
        return channels
    except Exception as e:
        log(f"getUpdates ошибка: {e}")
        return channels

    if not resp.get("ok"):
        log(f"getUpdates не ok: {resp}")
        return channels

    for upd in resp.get("result", []):
        uid = upd["update_id"]
        state["_last_update_id"] = max(state.get("_last_update_id", 0), uid)

        msg = upd.get("message") or upd.get("edited_message")
        if not msg:
            continue
        if str(msg.get("from", {}).get("id")) != MY_USER_ID:
            continue

        text = (msg.get("text") or "").strip()
        chat_id = msg["chat"]["id"]
        if not text:
            continue

        low = text.lower()

        if low.startswith("/list"):
            if channels:
                send_text(chat_id, "Каналы:\n" + "\n".join(
                    "• @" + c for c in sorted(channels)))
            else:
                send_text(chat_id, "Пусто. Кидай ссылку вида t.me/xxx")

        elif low.startswith("/add"):
            ch = extract_channel(text[4:].strip())
            if ch:
                channels.add(ch)
                send_text(chat_id, f"✅ Добавил @{ch}")
            else:
                send_text(chat_id, "Не понял. Формат: /add t.me/xxx")

        elif low.startswith("/remove") or low.startswith("/del"):
            arg = text.split(maxsplit=1)[1] if " " in text else ""
            ch = extract_channel(arg)
            if ch and ch in channels:
                channels.discard(ch)
                send_text(chat_id, f"🗑 Удалил @{ch}")
            else:
                send_text(chat_id, "Нет такого в списке")

        elif low.startswith("/start") or low.startswith("/help"):
            send_text(chat_id,
                "Кидай мне ссылку или @username — добавлю в список.\n"
                "/list — показать текущие\n"
                "/remove @name — удалить\n"
                "Проверка новых постов идёт раз в 5 минут.")

        else:
            # не команда — пробуем распарсить как канал
            ch = extract_channel(text)
            if ch:
                channels.add(ch)
                send_text(chat_id, f"✅ Добавил @{ch}")
            else:
                send_text(chat_id, "Не понял. Кидай t.me/xxx или @xxx")

    state["_channels"] = sorted(channels)
    return channels


# ─── Парсинг t.me/s/<channel> ────────────────────────────────

POST_RE = re.compile(
    r'data-post="([^"/]+)/(\d+)".*?'
    r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
    re.DOTALL,
)
TAG_RE = re.compile(r"<[^>]+>")
BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


def strip_tags(s):
    s = BR_RE.sub("\n", s)
    s = TAG_RE.sub("", s)
    return html.unescape(s).strip()


def parse_channel(channel):
    page = get(f"https://t.me/s/{channel}")
    posts = []
    for m in POST_RE.finditer(page):
        ch, num, raw = m.group(1), m.group(2), m.group(3)
        text = strip_tags(raw)
        if text:
            posts.append({"id": int(num), "text": text,
                          "link": f"https://t.me/{ch}/{num}"})
    posts.sort(key=lambda p: p["id"])
    return posts


# ─── ИИ-фильтр ────────────────────────────────────────────────

def ai_verdict(text):
    prompt = (
        f"Интересы пользователя:\n{USER_INTERESTS}\n\n"
        f"Пост:\n{text[:2000]}\n\n"
        f"Подходит? Ответь строго YES или NO."
    )
    try:
        resp = post_json(
            f"{AI_BASE_URL.rstrip('/')}/chat/completions",
            {
                "model": AI_MODEL,
                "messages": [
                    {"role": "system", "content": "Ты фильтр. Отвечай только YES или NO."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0,
                "max_tokens": 200,  # <-- БЫЛО 5
            },
            headers={
                "Authorization": f"Bearer {AI_API}",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/120.0",
                "Accept": "application/json",
            },
        )
        time.sleep(2)
        choice = resp["choices"][0]
        content = (choice.get("message", {}).get("content") or "").strip()
        finish = choice.get("finish_reason", "?")

        # Если пусто — выводим полный ответ, чтобы понять, что происходит
        if not content:
            log(f"  ИИ пустой ответ (finish={finish}). JSON: {json.dumps(resp)[:300]}")
            return AI_FAIL

        ans = content.upper()
        clean_ans = re.sub(r'^[^A-Z]+', '', ans)
        if clean_ans.startswith("YES"):
            return AI_YES
        if clean_ans.startswith("NO"):
            return AI_NO
        log(f"  ИИ вернул странное: '{content[:50]}' (finish={finish})")
        return AI_FAIL
    except Exception as e:
        log(f"  ИИ недоступен: {e}")
        time.sleep(1)
        return AI_FAIL
        
# ─── Обработка одного канала ──────────────────────────────────

def process_channel(channel, state):
    last = state.get(channel, 0)
    try:
        posts = parse_channel(channel)
    except Exception as e:
        log(f"[{channel}] не скачал: {e}")
        return

    fresh = [p for p in posts if p["id"] > last]
    if not fresh:
        return

    log(f"[{channel}] новых: {len(fresh)}")
    max_id = last
    
    for p in fresh:
        try:
            v = ai_verdict(p["text"])
            success = False  # Флаг: успешно ли мы разобрались с постом
            
            if v == AI_YES:
                if send(channel, p["text"], p["link"]):
                    log(f"  → #{p['id']} (фильтр)")
                    success = True
            elif v == AI_FAIL:
                if send(channel, p["text"], p["link"], note="⚠️ без фильтрации"):
                    log(f"  → #{p['id']} (без фильтра)")
                    success = True
            elif v == AI_NO:
                # Если ИИ сказал NO, пост нам не нужен, 
                # считаем это успехом, чтобы больше его не проверять.
                success = True
            
            if success:
                max_id = max(max_id, p["id"])
            else:
                log(f"  ⚠️ Не смог отправить #{p['id']}. Останавливаю канал, попробую в следующий раз.")
                break  # Прерываем цикл, чтобы не перезаписать state.json и не потерять этот пост
                
        except Exception as e:
            log(f"  ошибка #{p['id']}: {e}")
            break  # При любой ошибке тоже останавливаемся, чтобы не проскочить пост
            
    state[channel] = max_id


# ─── Точка входа ──────────────────────────────────────────────

def main():
    state = load_state()

    # 1. Забираем новые команды от владельца
    dynamic = handle_updates(state)

    # 2. Собираем итоговый список: статический + то, что добавил через бота
    all_channels = list(dict.fromkeys(CHANNELS + sorted(dynamic)))

    # 3. Гоним по всем
    for ch in all_channels:
        process_channel(ch, state)

    save_state(state)


if __name__ == "__main__":
    main()
