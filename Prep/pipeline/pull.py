"""
Pull ALL Gazette notices from DigitalNZ into one jsonl. No filtering here — every notice is saved
raw, so other categories stay available without a re-pull.

Resumable: the state file remembers the last committed byte, so a re-run truncates a half-written
tail and continues. Forward-only — past years are frozen, the current year is re-checked each run.

Run from Prep/, or via `docker compose run --rm prep ...`:
  python -m pipeline.pull               # resume from the state file -> current year
  python -m pipeline.pull --until 2005  # resume -> through 2005, then stop
  python -m pipeline.pull --reset       # wipe and start over from the beginning

PATTERN — one row (data/notices.jsonl):
  {"id":"2000-ds7832","code":"ds","type":"Removals","date":"2000-05-18",
   "title":"Equal Enterprise Limited (in liquidation)","nzbn":null,"company_number":"WN. 327693",
   "fulltext":"Notice of Application for Removal ...",
   "landing_url":"https://gazette.govt.nz/notice/id/2000-ds7832",
   "source":"New Zealand Gazette (CC BY 3.0 NZ)"}

PATTERN — state (data/notices.state.json):
  {"cursor_year":2001,"cursor_page":39,"offset":2054757,"seen":7413,"updated":"..."}
"""
import argparse
import json
import math
import os
import re
import time
from datetime import datetime, timezone

import requests

from shared import config as cfg
from shared import gazette

FIELDS = "dc_identifier,title,date,collection_title,landing_url,fulltext,description"

# NZBN = modern 13-digit key (post-2013). Company number = older format, sometimes
# regional ("Company No.: WN. 327693") or plain ("Company Number: 1234567").
NZBN = re.compile(r"NZBNs?[:.\s]+(\d{13})", re.I)
COMPANY_NUMBER = re.compile(r"Company\s+(?:Number|No)\.?[:.\s]+([A-Z]{0,3}\.?\s*\d+)", re.I)


def build_notice_row_from_record(record):
    """
    DigitalNZ record -> one notice row. Returns None only if there is no Notice Number.
    in : {"dc_identifier":["Notice Number: 2000-ds7832"], "title":"Equal Enterprise Limited",
          "date":["2000-05-18 12:00:00 UTC"], "fulltext":"Notice ... Company No.: WN. 327693 ...",
          "landing_url":"https://.../2000-ds7832"}
    out: {"id":"2000-ds7832","code":"ds","type":"Removals","date":"2000-05-18",
          "title":"Equal Enterprise Limited","nzbn":None,"company_number":"WN. 327693",
          "fulltext":"Notice ...","landing_url":"https://.../2000-ds7832",
          "source":"New Zealand Gazette (CC BY 3.0 NZ)"}
    """
    notice_id = gazette.extract_notice_id_from_dc_identifier(record.get("dc_identifier"))
    if not notice_id:
        return None

    code = gazette.get_type_code_from_notice_id(notice_id)

    body = (gazette.coerce_field_to_plain_text(record.get("fulltext"))
            or gazette.coerce_field_to_plain_text(record.get("description")))
    nzbn = NZBN.search(body)
    company = COMPANY_NUMBER.search(body)

    return {
        "id": notice_id,
        "code": code,
        "type": cfg.TYPES.get(code, code),
        "date": gazette.normalize_date_to_day(record.get("date")),
        "title": record.get("title"),
        "nzbn": nzbn.group(1) if nzbn else None,
        "company_number": company.group(1).strip() if company else None,
        "fulltext": body,
        "landing_url": record.get("landing_url"),
        "source": cfg.SOURCE_STAMP,
    }


def fetch_one_page_from_digitalnz(session, year, page):
    """
    Ask the API for one page (up to 100 records) of a single year.
    out: the 'search' object — result_count plus the page of records:
         {"result_count": 9277,
          "results": [
              {"dc_identifier": ["Notice Number: 2000-ds7832"],
               "title": "Equal Enterprise Limited (in liquidation)",
               "date": ["2000-05-18 12:00:00 UTC"],
               "fulltext": "Notice of Application for Removal ... Company No.: WN. 327693 ..."},
              ... one dict like the above per record, up to 100 ...
          ]}
    """
    params = {
        "and[primary_collection]": cfg.PRIMARY_COLLECTION,
        "and[year]": year,
        "sort": "syndication_date",   # for STABLE paging only — NOT publication order
        "direction": "asc",
        "per_page": cfg.PER_PAGE,
        "page": page,
        "fields": FIELDS,
    }
    response = session.get(cfg.BASE_URL, params=params, timeout=60)
    response.raise_for_status()
    return response.json()["search"]


def make_starting_state():
    """The state to begin with when nothing has been pulled yet."""
    return {"cursor_year": cfg.START_YEAR, "cursor_page": 1, "offset": 0, "seen": 0}


def load_saved_state_or_start_fresh():
    """Read the resume state, or a fresh one if the file is missing / a foreign shape."""
    if cfg.STATE_FILE.exists():
        saved = json.loads(cfg.STATE_FILE.read_text(encoding="utf-8"))
        if "cursor_year" in saved:            # ignore any legacy / foreign shape
            return saved
    return make_starting_state()


def write_state_file_atomically(state):
    """Save the resume state safely — write a .tmp then rename, so it's never half-written."""
    cfg.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    tmp = cfg.STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(cfg.STATE_FILE)


def trim_to_offset_then_open_append(offset):
    """Chop any half-written tail back to the committed byte mark, then open to append."""
    cfg.NOTICES_FILE.parent.mkdir(parents=True, exist_ok=True)
    if cfg.NOTICES_FILE.exists():
        with cfg.NOTICES_FILE.open("r+b") as handle:
            handle.truncate(offset)
    return cfg.NOTICES_FILE.open("ab")        # binary append -> tell() is an exact byte offset


def append_rows_and_return_new_offset(handle, rows):
    """Write rows as jsonl lines, flush to disk, and return the new byte offset."""
    for row in rows:
        handle.write((json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8"))
    handle.flush()
    os.fsync(handle.fileno())                 # on disk before we trust the offset
    return handle.tell()


# How far back to restart when the cursor is found past the last page. Results are appended in date
# order, so the tail pages are the ones that grow; a few pages of overlap is cheap and self-healing.
CURSOR_REWIND_PAGES = int(os.getenv("PULL_CURSOR_REWIND_PAGES", "3"))


def pull_one_year_page_by_page(session, handle, state, year):
    """Walk every page of a single year, checkpointing state after each page."""
    page = state["cursor_page"] if year == state["cursor_year"] else 1
    pages = None

    while pages is None or page <= pages:
        time.sleep(cfg.THROTTLE_SECONDS)
        search = fetch_one_page_from_digitalnz(session, year, page)
        if pages is None:
            pages = max(1, math.ceil(search["result_count"] / cfg.PER_PAGE))
            if page > pages:
                # The cursor sat past the end of an open year, so every run fetched a page that does
                # not exist, reported +0 and stepped one further out. Drop back to the live edge.
                page = max(1, pages - CURSOR_REWIND_PAGES)
                print(f"  {year} cursor was past page {pages} — rewinding to {page}")
                time.sleep(cfg.THROTTLE_SECONDS)
                search = fetch_one_page_from_digitalnz(session, year, page)

        rows = []
        for record in search["results"]:
            row = build_notice_row_from_record(record)
            if row:
                rows.append(row)

        offset = append_rows_and_return_new_offset(handle, rows)
        # Only step off a FULL page. A short page is the live edge of an open year — tomorrow's
        # notices land on it, so it has to be re-read next run rather than skipped past.
        at_live_edge = len(search["results"]) < cfg.PER_PAGE
        state.update(cursor_year=year, cursor_page=page if at_live_edge else page + 1,
                     offset=offset, seen=state["seen"] + len(rows))
        write_state_file_atomically(state)

        print(f"  {year} page {page}/{pages}  +{len(rows)}  (seen {state['seen']})")
        page += 1


def main():
    parser = argparse.ArgumentParser(description="Pull all Gazette notices from DigitalNZ.")
    parser.add_argument("--until", type=int, help="Run through this year, then stop.")
    parser.add_argument("--reset", action="store_true", help="Wipe and start over from the beginning.")
    args = parser.parse_args()

    if not cfg.API_KEY:
        raise SystemExit("Missing DIGITALNZ_API_KEY — check .env")

    this_year = datetime.now(timezone.utc).year
    until = args.until or this_year
    state = make_starting_state() if args.reset else load_saved_state_or_start_fresh()

    if state["cursor_year"] > until:
        print(f"Cursor at {state['cursor_year']} — already past {until}. Nothing to do.")
        return

    session = requests.Session()
    session.headers["Authentication-Token"] = cfg.API_KEY
    handle = trim_to_offset_then_open_append(state["offset"])
    print(f"Resuming at {state['cursor_year']} p{state['cursor_page']} (seen {state['seen']}) -> through {until}.")

    try:
        for year in range(state["cursor_year"], until + 1):
            pull_one_year_page_by_page(session, handle, state, year)
            if year < this_year:                      # past year done -> jump to next
                state.update(cursor_year=year + 1, cursor_page=1)
                write_state_file_atomically(state)
    except requests.HTTPError as error:
        status = error.response.status_code if error.response is not None else "?"
        print(f"[stop] HTTP {status} (rate-limited?) — state saved, rerun to resume.")
    except (requests.RequestException, KeyboardInterrupt) as error:
        print(f"[stop] {type(error).__name__} — state saved, rerun to resume.")
    finally:
        handle.close()

    print(f"Done -> {cfg.NOTICES_FILE}  (seen {state['seen']})")


if __name__ == "__main__":
    main()
