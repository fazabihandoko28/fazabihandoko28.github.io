# HANZ v2.2 Realtime Gateway

Upload semua isi patch ke root repository.

Commit:

`Add HANZ Realtime Gateway v2.2`

Expected new tests:

`7 PASS`

Tes replay:

```bash
python tools/replay_ticks.py --input samples/ticks.json
```

Patch bersifat additive dan tidak mengubah dashboard aktif.
