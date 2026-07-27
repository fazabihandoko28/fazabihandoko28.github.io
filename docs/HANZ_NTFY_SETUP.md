# HANZ ntfy Setup

1. Install aplikasi ntfy di Android.
2. Buat topic panjang dan sulit ditebak.
3. Subscribe ke topic itu pada server `https://ntfy.sh`.
4. Set environment variables pada server HANZ:

```text
HANZ_NTFY_SERVER=https://ntfy.sh
HANZ_NTFY_TOPIC=<topic-rahasia>
HANZ_DASHBOARD_URL=https://fazabihandoko28.github.io/
```

Opsional:

```text
HANZ_NTFY_TOKEN=<access-token>
```

Uji:

```bash
python tools/send_ntfy_test.py
```

Jalankan:

```bash
python tools/run_hanz_server_ntfy.py
```

Jangan simpan topic atau token rahasia di repository publik.
