#!/usr/bin/env python3
"""Build the static HANZ vacancy feed from public employer ATS endpoints."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUTPUT = Path(os.environ.get("HANZ_VACANCY_OUTPUT", "docs/vacancy/data/jobs.json"))
TIMEOUT = 25

SOURCES = [
    ("Grab", "smartrecruiters", "Grab"),
    ("Publicis Groupe", "smartrecruiters", "PublicisGroupe"),
    ("Bosch", "smartrecruiters", "BoschGroup"),
    ("Airwallex", "greenhouse", "airwallex"),
    ("Xendit", "lever", "xendit"),
    ("ShopBack", "lever", "shopback"),
]

ROLE_TERMS = re.compile(
    r"marketing|growth|brand|campaign|content|communications?|social media|"
    r"crm|seo|sem|acquisition|partnerships?|business development|commercial",
    re.I,
)
REGION_TERMS = re.compile(
    r"indonesia|jakarta|bandung|surabaya|bali|remote|asia|apac|singapore|"
    r"malaysia|philippines|thailand|vietnam",
    re.I,
)


def request_json(url: str) -> object:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "HANZ-Opportunity-Engine/3.0 (+https://hanzcuan.com/vacancy/)"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
        return json.load(response)


def smartrecruiters(company: str) -> list[dict]:
    url = f"https://api.smartrecruiters.com/v1/companies/{company}/postings?limit=100"
    payload = request_json(url)
    rows = payload.get("content", []) if isinstance(payload, dict) else []
    jobs = []
    for row in rows:
        location = row.get("location") or {}
        place = ", ".join(
            str(v) for v in (location.get("city"), location.get("country")) if v
        ) or "Location not stated"
        jobs.append({
            "id": f"sr-{row.get('id') or row.get('uuid')}",
            "title": row.get("name") or "Untitled role",
            "company": (row.get("company") or {}).get("name") or company,
            "location": place,
            "url": row.get("ref") or f"https://jobs.smartrecruiters.com/{company}",
            "published_at": row.get("releasedDate"),
        })
    return jobs


def greenhouse(board: str) -> list[dict]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs"
    payload = request_json(url)
    rows = payload.get("jobs", []) if isinstance(payload, dict) else []
    return [{
        "id": f"gh-{row.get('id')}",
        "title": row.get("title") or "Untitled role",
        "company": board.replace("-", " ").title(),
        "location": (row.get("location") or {}).get("name") or "Location not stated",
        "url": row.get("absolute_url"),
        "published_at": row.get("updated_at"),
    } for row in rows]


def lever(site: str) -> list[dict]:
    url = f"https://api.lever.co/v0/postings/{site}?mode=json"
    rows = request_json(url)
    if not isinstance(rows, list):
        return []
    return [{
        "id": f"lever-{row.get('id')}",
        "title": row.get("text") or "Untitled role",
        "company": site.replace("-", " ").title(),
        "location": (row.get("categories") or {}).get("location") or "Location not stated",
        "url": row.get("hostedUrl") or row.get("applyUrl"),
        "published_at": datetime.fromtimestamp(
            (row.get("createdAt") or 0) / 1000, timezone.utc
        ).isoformat() if row.get("createdAt") else None,
    } for row in rows]


FETCHERS = {"smartrecruiters": smartrecruiters, "greenhouse": greenhouse, "lever": lever}


def main() -> None:
    statuses, raw_jobs = [], []
    for label, provider, token in SOURCES:
        try:
            jobs = FETCHERS[provider](token)
            raw_jobs.extend(jobs)
            statuses.append({"name": label, "provider": provider, "ok": True, "jobs": len(jobs)})
        except (OSError, ValueError, urllib.error.URLError) as exc:
            statuses.append({"name": label, "provider": provider, "ok": False, "jobs": 0, "error": str(exc)[:160]})
        time.sleep(0.15)

    seen, matching = set(), []
    for job in raw_jobs:
        key = job.get("url") or job.get("id")
        if not key or key in seen:
            continue
        seen.add(key)
        if ROLE_TERMS.search(job["title"]) and REGION_TERMS.search(job["location"]):
            job["source_verified"] = True
            matching.append(job)

    matching.sort(key=lambda j: ("indonesia" not in j["location"].lower(), j["company"], j["title"]))
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources_attempted": len(SOURCES),
        "sources_healthy": sum(1 for s in statuses if s["ok"]),
        "raw_jobs": len(raw_jobs),
        "matching_jobs": len(matching),
        "source_status": statuses,
        "jobs": matching,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(matching)} matching jobs from {payload['sources_healthy']}/{len(SOURCES)} healthy sources")


if __name__ == "__main__":
    main()
