# Insta Saver

Веб-инструмент для скачивания видео из Instagram (Reels, посты, карусели, IGTV)
в максимальном качестве: лучший видеопоток и лучший аудиопоток склеиваются в MP4 через ffmpeg.
Дизайн — neumorphism, светлая и тёмная темы, адаптив под телефон.

**Сайт:** https://glone32482.github.io/insta-saver/

GitHub Pages хостит только страницу, а скачивание выполняет сервер с yt-dlp (ниже).
Адрес сервера и пароль вводятся в ⚙ на сайте и сохраняются на устройстве.
Можно сделать ссылку «всё в одном» для телефона:
`https://glone32482.github.io/insta-saver/?api=https://ВАШ-СЕРВЕР.onrender.com&key=ПАРОЛЬ`

## Деплой сервера в облако (доступ с любого устройства)

**Render** (бесплатно): New → Blueprint → выберите этот репозиторий. `render.yaml` всё настроит.

Переменные окружения:

| Переменная | Зачем |
|---|---|
| `APP_PASSWORD` | Пароль на вход (логин любой). Render сгенерирует его сам — посмотрите в Environment. |
| `INSTA_COOKIES` | Содержимое `cookies.txt` из браузера, где вы вошли в Instagram. Без него Instagram почти всегда блокирует серверные запросы. |

Как получить `cookies.txt`: расширение «Get cookies.txt LOCALLY» (Chrome/Firefox) → на instagram.com → Export.
Лучше использовать запасной аккаунт Instagram: куки дают полный доступ к нему.

Подойдёт любой хостинг с Docker (Fly.io, Railway, VPS): `docker build -t insta-saver . && docker run -p 8777:8777 -e APP_PASSWORD=... -e INSTA_COOKIES="$(cat cookies.txt)" insta-saver`

## Локальный запуск

    INSTA_COOKIES_BROWSER=chrome python3 server.py   # или safari / firefox / brave

Откройте http://127.0.0.1:8777. Нужны python3, yt-dlp и ffmpeg (`brew install yt-dlp ffmpeg`).
