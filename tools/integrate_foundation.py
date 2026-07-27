from __future__ import annotations

import argparse
import json

from hanz_app.foundation_integration import integrate_file


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Integrate legacy HANZ scan output with HANZ Foundation v2."
    )
    parser.add_argument("--input", required=True, help="Legacy latest.json")
    parser.add_argument("--output", required=True, help="Foundation decisions.json")
    args = parser.parse_args()

    result = integrate_file(args.input, args.output)
    total = sum(int(market.get("JUMLAH", 0)) for market in result["markets"])
    print(json.dumps(
        {"ok": True, "markets": len(result["markets"]), "decisions": total},
        ensure_ascii=False,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
