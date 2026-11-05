"""Follow-up suggestions: two or three clickable "what next?" questions under an answer.

How it works: at the end of its answer the model calls the tool `suggest_followups`. A click sends the suggestion
as the customer's own next message. There is no extra model call, so no extra delay or cost.

Why it is safe (each point has a test): suggestions are untrusted model output, because a customer (or text that
slipped into the knowledge base) can try to steer the model. So every suggestion passes `clean()` before it reaches a
button: plain text only, short, no links, email addresses, phone numbers, markup or hidden markers, nothing that
tries to instruct the assistant, no duplicates, never a repeat of the customer's own question. Anything that fails is
dropped silently; if nothing is left, no buttons are shown. Clicking only ever sends ordinary chat text through the
normal chat checks (rate limit, size limit, daily cap), so a button can do nothing a customer could not type.
"""
import re

from .feedback import EMAIL, PHONE

NAME = "suggest_followups"
MAX_ITEMS = 3
MIN_CHARS, MAX_CHARS = 6, 90

TOOL = {
    "name": NAME,
    "description": (
        "Show the customer two or three short follow-up questions they might want to ask next, as buttons. "
        "Call it after the full answer text, never instead of it."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "suggestions": {"type": "array", "items": {"type": "string"},
                            "description": "Two or three short questions in the customer's language, plain text only."},
        },
        "required": ["suggestions"],
    },
}

RULES = (
    "# Follow-up suggestions\n"
    "After you answer a question about our services, call the suggest_followups tool with two or three short "
    "questions the customer is likely to ask next. Write your full answer first, then call the tool. Each suggestion "
    "must be something the passages for this message can answer, in the customer's language, under 80 characters, "
    "plain text: no links, email addresses or phone numbers. Do not call the tool when you asked the customer a "
    "question or are collecting their details, after a hand-off, for an urgent issue, or when you could not answer."
)

CONTROL = re.compile(r"[\x00-\x1f\x7f​-‏ -‮⁠-⁯﻿]")
BAD_CHARS = re.compile(r"[<>{}\[\]`\\|]")
LINKY = re.compile(r"https?|www\.|://|\.(?:com|de|org|net|io|ru|xyz|top)\b|@|data:|javascript:", re.IGNORECASE)
# Words that only make sense in an attempt to instruct or probe the assistant (English and German).
INSTRUCTING = re.compile(
    r"\b(?:ignore|disregard|forget|override|bypass|jailbreak|pretend|roleplay|system\s*prompt|your\s+(?:rules|instructions|prompt)|"
    r"previous\s+instructions|developer\s+mode|reveal|password|api[\s_-]*key|secret|token|credentials?|"
    r"ignoriere|vergiss|umgehe|anweisungen|systemprompt|passwort|kennwort|schl[uü]ssel|geheim\w*)\b",
    re.IGNORECASE,
)


def _norm(text):
    return " ".join(re.findall(r"\w+", text.lower()))


def clean(items, question=""):
    """Return at most three safe suggestions from whatever the model sent (any type), or []."""
    if not isinstance(items, list):
        return []
    seen, out = {_norm(question)} if question else set(), []
    for item in items:
        if not isinstance(item, str):
            continue
        text = " ".join(CONTROL.sub(" ", item).split())
        if not (MIN_CHARS <= len(text) <= MAX_CHARS):
            continue
        if BAD_CHARS.search(text) or LINKY.search(text) or EMAIL.search(text) or PHONE.search(text) or INSTRUCTING.search(text):
            continue
        if not any(ch.isalpha() for ch in text):
            continue
        key = _norm(text)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) == MAX_ITEMS:
            break
    return out
