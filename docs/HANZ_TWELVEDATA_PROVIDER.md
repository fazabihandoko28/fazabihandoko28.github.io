# HANZ Twelve Data Provider v3.1

## Alur

`Twelve Data WebSocket -> Realtime Gateway -> Opportunity Radar -> Event Engine`

## Instal dependency

```bash
pip install -r requirements-realtime.txt
```

## Secret server

```text
HANZ_TWELVEDATA_API_KEY=<api-key>
HANZ_TWELVEDATA_SYMBOLS=<provider-symbol-1>,<provider-symbol-2>
```

Jangan menyimpan API key di repository atau dashboard.

## Jalankan

```bash
python tools/run_twelvedata_radar.py \
  --market BEI \
  --rank-seconds 15
```

Dengan pemetaan simbol:

```bash
python tools/run_twelvedata_radar.py \
  --market BEI \
  --symbol-map config/twelvedata_symbols.csv
```

## Penting

Nama simbol dan cakupan bursa harus dikonfirmasi melalui akun Twelve Data.
WebSocket penuh dan jumlah simbol simultan bergantung pada paket provider.
Provider tidak menjamin bahwa semua saham BEI tersedia pada paket dasar.

## Proteksi

- invalid tick rejection;
- status-message handling;
- heartbeat;
- reconnect exponential backoff;
- API key hanya di environment;
- symbol alias mapping;
- snapshot radar berkala.
