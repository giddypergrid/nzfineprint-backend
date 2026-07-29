"""DigitalNZ Gazette record-parsing helpers (shared by every pull)."""
import re

NOTICE_NUMBER = re.compile(r"Notice Number:\s*(\d{4}-[a-z]{2}\d+)", re.I)


def extract_notice_id_from_dc_identifier(dc_identifier):
    """
    Pull the Gazette notice id out of DigitalNZ's dc_identifier list.
    in : ["Notice Number: 2000-al123", "Issue Number: 5"]
    out: "2000-al123"   (lowercased; None if there is no Notice Number)
    """
    for item in dc_identifier or []:
        match = NOTICE_NUMBER.search(item)
        if match:
            return match.group(1).lower()
    return None


def get_type_code_from_notice_id(notice_id):
    """
    Read the 2-letter notice-type code embedded in a notice id.
    in : "2000-al123"
    out: "al"
    """
    return notice_id.split("-", 1)[1][:2]


def normalize_date_to_day(date_field):
    """
    Keep only the YYYY-MM-DD day (handles both DigitalNZ date formats).
    in : ["2015-06-11 12:00:00 UTC"]  or  ["2025-10-14T00:00:00Z"]
    out: "2015-06-11"                 or  "2025-10-14"   (None if empty)
    """
    return date_field[0][:10] if date_field else None


def coerce_field_to_plain_text(value):
    """
    DigitalNZ returns some fields as a list, some as a bare string — make it plain text.
    in : ["Notice of ..."]   or   "Notice of ..."   or   None
    out: "Notice of ..."     or   "Notice of ..."   or   ""
    """
    if isinstance(value, list):
        return value[0] if value else ""
    return value or ""
