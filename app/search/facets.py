"""The normalized enums enrichment wrote into the DB. The query parser may only choose filter
values from these exact lists, so a parsed filter always matches real stored data. Keep in sync
with Prep/pipeline/enrich_prompt.py — same strings, same order."""

EVENT_CATEGORIES = [
    "liquidation", "receivership", "administration", "bankruptcy",
    "cessation", "company_removal", "creditor_meeting", "claim_deadline",
    "legislation", "land", "charity_or_society", "appointment", "other",
]

ACTION_TYPES = [
    "application_filed", "liquidator_appointed", "liquidator_released",
    "receiver_appointed", "receiver_released", "administrator_appointed",
    "administrator_released", "bankruptcy_declared", "company_struck_off",
    "business_ceased", "meeting_called", "deadline_set", "rule_made",
    "land_action", "status_changed", "other",
]
