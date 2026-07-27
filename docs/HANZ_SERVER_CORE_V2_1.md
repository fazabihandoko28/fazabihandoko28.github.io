# HANZ Server Core v2.1

Alur: `decisions.json -> Server Core -> Event Engine -> Telegram/API -> HP`.

Jalankan file: `python tools/process_decisions_file.py --input docs/data/decisions.json`

Server: `python tools/run_hanz_server.py --port 8080`

Endpoint: `/health`, `/events`, `/decision`, `/decisions`.

Telegram memakai `HANZ_TELEGRAM_BOT_TOKEN` dan `HANZ_TELEGRAM_CHAT_ID`.
