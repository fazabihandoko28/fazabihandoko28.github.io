# HANZ v1.3 Executive Dashboard Patch

This patch redesigns the generated dashboard without changing the scan engine or workflow.

## Replace / add

- `src/hanz_app/render_report.py`
- `tests/test_render_report_executive_v13.py`
- `CHANGELOG.md`

## Main changes

- Large **Today's Decision** panel with direct action guidance.
- Cleaner market posture, health, exposure, and quality summary.
- Explicit **What To Do** instruction on every stock card.
- Quality progress meter.
- Premium institutional visual hierarchy.
- Improved mobile sticky decision card and swipeable stock cards.
- No external libraries, images, fonts, or API dependencies.

## After upload

1. Wait for **HANZ CI** to turn green.
2. Run **HANZ Paper Scan** once.
3. Refresh the live site with a hard refresh or private/incognito window.
