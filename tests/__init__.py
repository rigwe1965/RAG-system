import os

# Tests must not write chats or activity numbers into the real sessions/ and metrics/ folders;
# tests that need them switch them on themselves, in a temporary folder.
os.environ.setdefault("PERSIST_SESSIONS", "off")
os.environ.setdefault("METRICS", "off")
