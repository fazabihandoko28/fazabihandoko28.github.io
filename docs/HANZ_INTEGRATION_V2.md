# HANZ Foundation Integration v2.0

## Tujuan

Patch ini menghubungkan output scanner lama dengan fondasi baru tanpa mengganti
scanner atau dashboard aktif.

## Input

`artifacts/paper_scans/latest.json`

## Output

`dashboard/data/decisions.json`

## Alur

1. Membaca kandidat dan watchlist dari format JSON lama.
2. Mengubah sinyal lama menjadi `EvidenceVector`.
3. Menjalankan `DecisionEngine`.
4. Menghasilkan label dashboard Indonesia:
   - `AWAL`
   - `SIAGA`
   - `EKSEKUSI`
   - `TAHAN`
   - `LEPAS`
   - `JUAL`
   - `LEWATI`
   - `DATA MINIM`
5. Menyimpan keputusan tanpa mengubah `dashboard/index.html`.

## Catatan

Patch ini belum memperluas universe BEI. Tujuannya mengaktifkan fondasi secara
aman terlebih dahulu. Full-universe scanner adalah patch terpisah.
