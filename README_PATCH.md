# HANZ v1.1 Decision Intelligence Patch

Upload/replace these files in the same repository paths:

- `src/hanz_app/decision_intelligence.py`
- `src/hanz_app/render_report.py`
- `tests/test_decision_intelligence.py`
- `tests/test_render_report_v11.py`
- `pyproject.toml`
- `CHANGELOG.md`

Commit message:

`Add evidence quality, market posture, and research trade plans v1.1`

Then confirm HANZ CI is green and run `HANZ Paper Scan` once.

The dashboard will add quality scores, grades, market posture, entry zones, research stops, targets, and no-candidate explanations. Quality is evidence alignment—not a claimed probability of profit.
