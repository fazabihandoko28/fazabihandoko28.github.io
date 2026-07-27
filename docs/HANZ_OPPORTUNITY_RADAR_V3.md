# HANZ Opportunity Radar v3.0

## Fungsi

Opportunity Radar menerima state dari Realtime Gateway lalu:

1. membuang state basi;
2. hanya memproses simbol yang berubah;
3. menghitung evidence cepat;
4. menentukan `AWAL`, `SIAGA`, atau `EKSEKUSI`;
5. mengurutkan peluang terbaik;
6. mencatat perubahan status;
7. meneruskan keputusan ke Event Engine.

## Output

```json
{
  "TOTAL": 900,
  "RADAR": [
    {
      "symbol": "TINS",
      "status": "SIAGA",
      "evidence": 72,
      "risk": "SEDANG"
    }
  ]
}
```

## Integrasi

`RealtimeGateway -> OpportunityRadar -> RadarDecisionBridge -> EventEngine`

## Catatan

Patch ini belum menyediakan data feed pasar. Ia mengaktifkan radar berbasis
state realtime yang masuk dari provider.
