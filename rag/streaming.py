"""Helpers for streaming answers to the customer while the model is still writing.

The model puts hidden markers in its text ([[book]], [[gap]]). The customer must never see them, not even
half of one that arrives in two pieces, so text that could still turn into a marker is held back until we know.

    f = MarkerFilter()
    f.feed("Pick a time.\n[[bo")   -> "Pick a time.\n"     ("[[bo" is held back)
    f.feed("ok]]")                 -> ""                    (a complete marker: removed)
    f.flush()                      -> ""                    (end of answer)
"""
import re

NAMES = "book|gap"
FULL = re.compile(r"[ \t]*\[\[\s*(?:" + NAMES + r")\s*\]\][ \t]*", re.IGNORECASE)
# the tail of a text that might still become a marker: "[", "[[", "[[b", "[[bo", "[[ga", "[[gap]", ...
PARTIAL = re.compile(r"[ \t]*\[(?:\[\s*(?:b(?:o(?:o(?:k)?)?)?|g(?:a(?:p)?)?)?\s*(?:\](?:\])?)?)?$", re.IGNORECASE)


class MarkerFilter:
    def __init__(self):
        self.buf = ""

    def feed(self, text):
        """Add text from the model. Returns the part that is safe to show now."""
        self.buf = FULL.sub("", self.buf + text)
        tail = PARTIAL.search(self.buf)
        if tail:
            safe, self.buf = self.buf[:tail.start()], self.buf[tail.start():]
        else:
            safe, self.buf = self.buf, ""
        return safe

    def flush(self):
        """The answer is over: whatever was held back was not a marker after all, so release it."""
        rest, self.buf = FULL.sub("", self.buf), ""
        return rest

    def reset(self):
        self.buf = ""
