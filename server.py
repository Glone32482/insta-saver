#!/usr/bin/env python3
"""Локальный сервер для скачивания видео из Instagram в максимальном качестве.

Использует yt-dlp (выбор лучшего видео + лучшего аудио) и ffmpeg (склейка в mp4).
Запуск:  python3 server.py   →   http://127.0.0.1:8777

Если Instagram требует вход (приватные посты, stories, лимиты):
  INSTA_COOKIES_BROWSER=chrome python3 server.py      # взять куки из браузера
  или положить cookies.txt (формат Netscape) рядом с server.py

На сервере (Render и т.п.):
  INSTA_COOKIES   — содержимое cookies.txt
  APP_PASSWORD    — пароль на вход (HTTP Basic, логин любой)
"""
import base64
import hmac
import json
import os
import shutil
import subprocess
import tempfile
import urllib.parse
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8777"))
ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
COOKIES_FILE = ROOT / "cookies.txt"
ALLOWED_HOSTS = {"instagram.com", "www.instagram.com", "m.instagram.com", "instagr.am"}
TIMEOUT = 300
PASSWORD = os.environ.get("APP_PASSWORD", "")

# Куки из переменной окружения (для облачного хостинга, где нет файла)
if os.environ.get("INSTA_COOKIES"):
    COOKIES_FILE = Path(tempfile.gettempdir()) / "insta_cookies.txt"
    COOKIES_FILE.write_text(os.environ["INSTA_COOKIES"].replace("\\n", "\n").strip() + "\n")

# Лучшее видео + лучшее аудио; если раздельных потоков нет — лучший единый файл.
FORMAT = "bv*+ba/b"
SORT = "res,fps,vbr,abr"


def yt_dlp_base():
    exe = shutil.which("yt-dlp")
    if not exe:
        raise RuntimeError("yt-dlp не найден. Установите: brew install yt-dlp")
    args = [exe, "--no-warnings", "--no-progress", "--ignore-config"]
    browser = os.environ.get("INSTA_COOKIES_BROWSER")
    if browser:
        args += ["--cookies-from-browser", browser]
    elif COOKIES_FILE.exists():
        args += ["--cookies", str(COOKIES_FILE)]
    return args


def validate_url(raw):
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("Вставьте ссылку на пост, Reels или IGTV")
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    parsed = urllib.parse.urlparse(raw)
    if (parsed.hostname or "").lower() not in ALLOWED_HOSTS:
        raise ValueError("Это не ссылка Instagram")
    # Убираем трекинговые параметры (?igsh=..., ?utm_...)
    return urllib.parse.urlunparse(parsed._replace(query="", fragment=""))


def friendly_error(stderr):
    text = stderr.strip().splitlines()
    msg = text[-1] if text else "Неизвестная ошибка"
    low = stderr.lower()
    if "login" in low or "cookies" in low or "rate-limit" in low:
        return ("Instagram требует авторизацию для этой ссылки. Перезапустите сервер с "
                "INSTA_COOKIES_BROWSER=chrome (или safari/firefox) либо положите cookies.txt рядом с server.py.")
    if "no video" in low or "there is no video" in low:
        return "В этом посте нет видео — только фото."
    if "unsupported url" in low:
        return "Ссылка не поддерживается. Нужна ссылка на пост, Reels или IGTV."
    return msg.removeprefix("ERROR: ")


def best_format(info):
    """Ищет параметры итогового качества (видео-поток с максимальным разрешением)."""
    fmts = [f for f in info.get("formats") or [] if f.get("vcodec") not in (None, "none")]
    if not fmts:
        return {"width": info.get("width"), "height": info.get("height")}
    best = max(fmts, key=lambda f: ((f.get("height") or 0) * (f.get("width") or 0),
                                    f.get("fps") or 0, f.get("tbr") or 0))
    return {"width": best.get("width"), "height": best.get("height"),
            "fps": best.get("fps"), "vcodec": best.get("vcodec")}


def describe(entry, index):
    q = best_format(entry)
    size = entry.get("filesize") or entry.get("filesize_approx")
    return {
        "index": index,
        "id": entry.get("id"),
        "title": entry.get("title") or entry.get("description") or "",
        "thumbnail": entry.get("thumbnail"),
        "duration": entry.get("duration"),
        "size": size,
        **q,
    }


def fetch_info(url):
    proc = subprocess.run(yt_dlp_base() + ["-J", "-f", FORMAT, "-S", SORT, url],
                          capture_output=True, text=True, timeout=TIMEOUT)
    if proc.returncode != 0:
        raise RuntimeError(friendly_error(proc.stderr))
    info = json.loads(proc.stdout)
    entries = info.get("entries")
    items = [describe(e, i + 1) for i, e in enumerate(entries) if e] if entries else [describe(info, 0)]
    return {
        "uploader": info.get("uploader") or info.get("channel") or
                    (entries[0].get("uploader") if entries else None),
        "description": (info.get("description") or "")[:300],
        "items": items,
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(STATIC), **kw)

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        # CORS: фронтенд может жить на другом домене (GitHub Pages)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "X-Password")
        self.send_header("Access-Control-Expose-Headers", "Content-Length, X-Filename")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def authorized(self):
        if not PASSWORD:
            return True
        pwd = self.headers.get("X-Password", "")
        header = self.headers.get("Authorization", "")
        if not pwd and header.startswith("Basic "):
            try:
                pwd = base64.b64decode(header[6:]).decode().partition(":")[2]
            except ValueError:
                pass
        if pwd and hmac.compare_digest(pwd.encode(), PASSWORD.encode()):
            return True
        if self.path.startswith("/api/"):
            self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "Неверный пароль сервера", "auth": True})
            return False
        self.send_response(HTTPStatus.UNAUTHORIZED)
        self.send_header("WWW-Authenticate", 'Basic realm="Insta Saver", charset="UTF-8"')
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    def do_GET(self):
        if not self.authorized():
            return
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        try:
            if parsed.path == "/api/ping":
                return self.send_json(200, {"ok": True})
            if parsed.path == "/api/info":
                return self.send_json(200, fetch_info(validate_url(params.get("url", [""])[0])))
            if parsed.path == "/api/download":
                return self.download(validate_url(params.get("url", [""])[0]),
                                     int(params.get("index", ["0"])[0] or 0))
        except ValueError as e:
            return self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(e)})
        except subprocess.TimeoutExpired:
            return self.send_json(HTTPStatus.GATEWAY_TIMEOUT, {"error": "Instagram слишком долго отвечает"})
        except RuntimeError as e:
            return self.send_json(HTTPStatus.BAD_GATEWAY, {"error": str(e)})
        return super().do_GET()

    def download(self, url, index):
        tmp = tempfile.mkdtemp(prefix="igdl-")
        try:
            args = yt_dlp_base() + ["-f", FORMAT, "-S", SORT, "--merge-output-format", "mp4",
                                    "-o", os.path.join(tmp, "%(uploader|instagram)s_%(id)s.%(ext)s")]
            args += ["--playlist-items", str(index)] if index > 0 else ["--no-playlist"]
            proc = subprocess.run(args + [url], capture_output=True, text=True, timeout=TIMEOUT)
            files = [p for p in Path(tmp).iterdir() if p.is_file() and not p.name.endswith(".part")]
            if proc.returncode != 0 or not files:
                raise RuntimeError(friendly_error(proc.stderr or "Файл не был скачан"))
            path = max(files, key=lambda p: p.stat().st_size)
            name = path.name
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4" if name.endswith(".mp4") else "application/octet-stream")
            self.send_header("Content-Length", str(path.stat().st_size))
            self.send_header("Content-Disposition",
                             f"attachment; filename*=UTF-8''{urllib.parse.quote(name)}")
            self.send_header("X-Filename", urllib.parse.quote(name))
            self.end_headers()
            with path.open("rb") as f:
                shutil.copyfileobj(f, self.wfile, 1024 * 256)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Instagram Downloader → http://{HOST}:{PORT}" + ("  (с паролем)" if PASSWORD else ""))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
