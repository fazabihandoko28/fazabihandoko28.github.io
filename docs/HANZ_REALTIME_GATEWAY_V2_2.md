# HANZ Realtime Gateway v2.2

## Fungsi

Patch ini menambahkan mesin yang menerima tick ter-normalisasi lalu:

1. memvalidasi tick;
2. memperbarui state tanpa menghitung ulang semuanya;
3. mendeteksi anomali harga/volume;
4. memasukkan saham ke Opportunity Queue;
5. menjadwalkan perhitungan cepat dan berat secara terpisah;
6. menjaga posisi aktif melalui Portfolio Guardian.

## Komponen

- `RealtimeGateway`
- `RollingWindow`
- `OpportunityQueue`
- `SmartScheduler`
- `PortfolioGuardian`
- `TickProvider`

## Belum termasuk

- koneksi data pasar real-time;
- deployment cloud;
- Firebase push;
- eksekusi order otomatis.

Provider data akan dipasang melalui kontrak `TickProvider`.
