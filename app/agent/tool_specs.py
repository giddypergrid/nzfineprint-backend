"""OpenAI-format tool schemas the agent sees. Descriptions are written for the model's judgment —
when to reach for each — and deliberately avoid exposing storage internals. The enums must match
facets.py (the enrichment vocabulary)."""
from app.search.facets import EVENT_CATEGORIES, ACTION_TYPES

# Every tool carries this. Asking for the stage line as an ARGUMENT is the only reliable way to get
# it: the model returns tool calls with empty message content, so narration in the reply text is
# routinely lost. As an argument it always arrives, in the model's own words.
_NARRATION = {
    "type": "string",
    "description": "One short present-tense line, in plain language, telling the user what you are "
                   "doing right now — e.g. 'Looking for Sacred Hill in the record…' or 'Reading the "
                   "receivership notice in full…'. Shown to them live while they wait. Never mention "
                   "tools, searching, databases, or any system detail.",
}

TOOL_SPECS = [
    {"type": "function", "function": {
        "name": "search_notices",
        "description": "Search the public record for notices matching a query. Returns a compact "
                       "list (headline, date, category, importance) — use it to scan widely and find "
                       "leads, then look closer at the ones that matter. Good for topics, company "
                       "names, or plain-language descriptions of a situation.",
        "parameters": {"type": "object", "properties": {
            "narration": _NARRATION,
            "query": {"type": "string", "description": "What to look for — a name, a topic, or a "
                                                        "description of the situation."},
            "event_category": {"type": "string", "enum": list(EVENT_CATEGORIES),
                               "description": "Restrict to one kind of event, if the question implies one."},
            "action_taken": {"type": "string", "enum": list(ACTION_TYPES),
                             "description": "Restrict to one specific action, if implied."},
            "date_from": {"type": "string", "description": "Earliest date, YYYY-MM-DD. Use for 'recent'."},
            "date_to": {"type": "string", "description": "Latest date, YYYY-MM-DD."},
            "min_significance": {"type": "integer", "description": "0-100. Raise it for 'notable/big/"
                                                                   "serious' to skip routine notices."},
        }, "required": ["narration", "query"]}}},

    {"type": "function", "function": {
        "name": "get_notice",
        "description": "Read one notice in full — the plain-language explanation, the original text, "
                       "everyone named, and the source link. Use after a search to understand a "
                       "specific notice that looks important.",
        "parameters": {"type": "object", "properties": {
            "narration": _NARRATION,
            "notice_id": {"type": "string", "description": "The id from a search result."},
        }, "required": ["narration", "notice_id"]}}},

    {"type": "function", "function": {
        "name": "get_company_history",
        "description": "Get every notice for one company, oldest first — its full timeline in the "
                       "record. Best way to see whether trouble was a one-off or a long decline. "
                       "Give whichever identifier you have.",
        "parameters": {"type": "object", "properties": {
            "narration": _NARRATION,
            "nzbn": {"type": "string", "description": "13-digit company number, if known."},
            "company_number": {"type": "string", "description": "Older company id, if known."},
            "name": {"type": "string", "description": "Company name (partial is fine)."},
        }, "required": ["narration"]}}},

    {"type": "function", "function": {
        "name": "find_related_parties",
        "description": "From one notice, see everyone named in it and what OTHER notices name the "
                       "same people or companies — surfaces repeat directors, connected companies, "
                       "hidden links. Use to answer 'who is behind this' or 'what else are they "
                       "tied to'.",
        "parameters": {"type": "object", "properties": {
            "narration": _NARRATION,
            "notice_id": {"type": "string", "description": "The notice to start from."},
        }, "required": ["narration", "notice_id"]}}},
]
