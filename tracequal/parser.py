"""Parse chat transcripts from Claude exports and TraceQual text fixtures.

A "transcript" is the back-and-forth record of a conversation. This module's job
is to take that conversation in any of several file formats and turn it into one
simple, uniform Python structure (a list of ``Turn`` dictionaries) that the rest
of the project can work with.
"""

# `from __future__ import annotations` lets us write modern type hints (like
# `str | None`) that work on older Python versions. It must be the first import.
from __future__ import annotations

import json  # for reading/writing JSON-formatted text
import re  # "regular expressions": a mini-language for matching text patterns
from pathlib import Path  # an object-oriented way to handle file paths
from typing import Any, Literal, TypedDict  # tools for describing data shapes

# `Speaker` is a type alias: a value labeled "researcher" or "assistant", nothing else.
# This documents intent and lets tools catch typos like "reseacher".
Speaker = Literal["researcher", "assistant"]

# A compiled regular expression that recognizes a turn header line in plain-text
# fixtures, e.g. "Turn 3 (R): some text" or "**Turn 3 (AI):** some text".
# The parentheses create three "capture groups" we read out later:
#   group(1) = the turn number, group(2) = who spoke, group(3) = the rest of the line.
# `\*{0,2}` allows the optional markdown bold markers (**). re.IGNORECASE = case-insensitive.
TURN_HEADER_PATTERN = re.compile(
    r"^\*{0,2}Turn\s+(\d+)\s+\((R|AI|human|assistant|researcher)\):\*{0,2}\s*(.*)$",
    re.IGNORECASE,
)


class Turn(TypedDict):
    """One turn in a parsed chat transcript.

    A ``TypedDict`` is just a regular dictionary, but we spell out which keys it
    must have and what type each value is. So every Turn is a dict shaped like:
    ``{"turn_id": 1, "speaker": "researcher", "content": "...", "timestamp": None}``.
    """

    turn_id: int  # 1, 2, 3, ... in conversation order
    speaker: Speaker  # who is talking: "researcher" or "assistant"
    content: str  # the actual text of what was said
    timestamp: str | None  # when it was said, if known; otherwise None


def parse_chat(path: Path | str) -> list[Turn]:
    """Parse a chat transcript file into a list of turn dictionaries.

    Format is determined by file extension only (no content sniffing):

    - ``.json``: Claude or API-style JSON exports
    - ``.md``, ``.txt``: TraceQual plain-text or markdown fixtures

    Supports Claude JSON exports (``chat_messages`` or OpenAI-style ``messages``)
    and TraceQual plain-text or markdown fixtures (``Turn N (R): ...`` lines).
    """
    file_path = Path(path)  # accept either a string or a Path; normalize to Path
    text = file_path.read_text(encoding="utf-8")  # read the whole file into a string
    suffix = file_path.suffix.lower()  # the extension, e.g. ".json" (lowercased)

    # Pick a parser based purely on the file extension.
    if suffix == ".json":
        return _parse_json_transcript(text)
    if suffix in {".md", ".txt"}:
        # Guard against a common mistake: JSON content saved with a .txt name.
        # `lstrip()` removes leading whitespace so we can check the first real char.
        if suffix == ".txt" and text.lstrip().startswith("{"):
            raise ValueError(
                "File extension is .txt but content looks like JSON. "
                "Rename to .json or pass format explicitly."
            )
        return _parse_text_transcript(text)

    # Any other extension is something we don't know how to read.
    raise ValueError(
        f"Unsupported file extension {suffix!r}. "
        "Use .json, .md, or .txt."
    )


def parse_chat_content(
    text: str,
    *,
    format: Literal["json", "text"] | None = None,
) -> list[Turn]:
    """Parse transcript text when the caller has content but not a file path.

    Useful when the text came from, say, a web upload or a text box instead of a
    file on disk, so there is no extension to look at.
    """
    stripped = text.strip()  # text with surrounding whitespace removed
    if not stripped:
        raise ValueError("Transcript content is empty.")

    # If the caller explicitly told us the format, trust them.
    if format == "json":
        return _parse_json_transcript(text)
    if format == "text":
        return _parse_text_transcript(text)

    # Otherwise, guess: JSON content always begins with "{" or "[".
    if stripped.startswith(("{", "[")):
        return _parse_json_transcript(text)
    return _parse_text_transcript(text)


def format_transcript(turns: list[Turn]) -> str:
    """Format parsed turns for injection into the extraction prompt.

    This is the reverse of parsing: it turns the list of Turn dicts back into one
    clean text block that we can paste into the prompt we send to the AI model.
    """
    blocks: list[str] = []  # one formatted line per turn
    for turn in turns:
        # Use a short label ("R" for researcher, "AI" for assistant) in the output.
        label = "R" if turn["speaker"] == "researcher" else "AI"
        blocks.append(f"Turn {turn['turn_id']} ({label}): {turn['content']}")
    # Join the blocks with a blank line between each so they're easy to read.
    return "\n\n".join(blocks)


def _parse_json_transcript(text: str) -> list[Turn]:
    """Parse Claude or API-style JSON chat exports.

    Different tools export chats in slightly different JSON shapes. This function
    sniffs out which shape we got and hands it to the matching helper. (Note the
    leading underscore in the name: by convention that marks a "private" helper
    meant for use inside this module, not by outside code.)
    """
    payload = json.loads(text)  # turn the JSON text into Python lists/dicts

    # Case 1: the top level is a list (e.g. a list of conversations).
    if isinstance(payload, list):
        if not payload:
            raise ValueError("JSON transcript list is empty.")
        # Look at the first item to figure out which known shape this is.
        if isinstance(payload[0], dict) and "chat_messages" in payload[0]:
            return _parse_chat_messages(payload[0]["chat_messages"])
        if isinstance(payload[0], dict) and "messages" in payload[0]:
            return _parse_role_messages(payload[0]["messages"])
        if isinstance(payload[0], dict) and _looks_like_message(payload[0]):
            return _parse_message_objects(payload)
        raise ValueError("Unsupported JSON transcript list format.")

    # Case 2: the top level should otherwise be a single object (a dict).
    if not isinstance(payload, dict):
        raise ValueError("JSON transcript must be an object or a list of objects.")

    # Check known keys, in order, to decide which export format this is.
    if "chat_messages" in payload:
        return _parse_chat_messages(payload["chat_messages"])
    if "messages" in payload:
        return _parse_role_messages(payload["messages"])
    if "chats" in payload:
        return _parse_chats_export(payload["chats"])
    raise ValueError(
        "Unsupported JSON transcript format. Expected chat_messages or messages."
    )


def _parse_chat_messages(messages: list[dict[str, Any]]) -> list[Turn]:
    """Parse Claude userscript-style exports with sender/text fields."""
    turns: list[Turn] = []
    # `enumerate(..., start=1)` walks the list while also counting 1, 2, 3, ...
    # so we get both the running number (index) and the message itself.
    for index, message in enumerate(messages, start=1):
        # `.get("sender", "")` reads the key but returns "" if it's missing,
        # avoiding a crash. `.lower()` makes the comparison case-insensitive.
        sender = str(message.get("sender", "")).lower()
        # Map the many possible names for each role onto our two canonical labels.
        if sender in {"human", "user", "researcher", "r"}:
            speaker: Speaker = "researcher"
        elif sender in {"assistant", "ai", "claude"}:
            speaker = "assistant"
        else:
            raise ValueError(f"Unknown sender {sender!r} in chat_messages[{index - 1}].")

        # The message body might live under "text" or "content"; try "text" first.
        content = _extract_message_text(message.get("text", message.get("content", "")))
        if not content.strip():
            continue  # skip empty messages entirely

        turns.append(
            {
                "turn_id": index,
                "speaker": speaker,
                "content": content.strip(),
                "timestamp": _normalize_timestamp(message.get("created_at")),
            }
        )
    return turns


def _parse_role_messages(messages: list[dict[str, Any]]) -> list[Turn]:
    """Parse OpenAI-style role/content message arrays."""
    turns: list[Turn] = []
    # We number turns ourselves here (turn_id) because we skip some messages,
    # so the original list position wouldn't give a clean 1, 2, 3 sequence.
    turn_id = 0
    for message in messages:
        role = str(message.get("role", "")).lower()
        # "system" and "tool" messages are setup/plumbing, not conversation — skip.
        if role in {"system", "tool"}:
            continue
        if role in {"user", "human", "researcher"}:
            speaker: Speaker = "researcher"
        elif role in {"assistant", "ai"}:
            speaker = "assistant"
        else:
            raise ValueError(f"Unknown role {role!r} in messages.")

        content = _extract_message_text(message.get("content", message.get("text", "")))
        if not content.strip():
            continue

        turn_id += 1  # only count turns we actually keep
        turns.append(
            {
                "turn_id": turn_id,
                "speaker": speaker,
                "content": content.strip(),
                "timestamp": _normalize_timestamp(
                    message.get("created_at", message.get("timestamp"))
                ),
            }
        )
    return turns


def _parse_chats_export(chats: list[dict[str, Any]]) -> list[Turn]:
    """Parse browser-export JSON with prompt/response chat blocks."""
    turns: list[Turn] = []
    turn_id = 0
    for chat in chats:
        # In this format the role is stored under "type" instead of "sender"/"role".
        chat_type = str(chat.get("type", "")).lower()
        if chat_type in {"prompt", "human", "user"}:
            speaker: Speaker = "researcher"
        elif chat_type in {"response", "assistant", "ai"}:
            speaker = "assistant"
        else:
            continue  # unknown block type: skip rather than crash

        content = _extract_message_text(chat.get("message", chat.get("text", "")))
        if not content.strip():
            continue

        turn_id += 1
        turns.append(
            {
                "turn_id": turn_id,
                "speaker": speaker,
                "content": content.strip(),
                "timestamp": _normalize_timestamp(chat.get("created_at")),
            }
        )
    return turns


def _parse_message_objects(messages: list[dict[str, Any]]) -> list[Turn]:
    """Parse a bare list of message objects when role fields are present.

    `all(... for ...)` is True only if the condition holds for every item. So
    we route based on whether every message uses "role" or every one uses "sender".
    """
    if all("role" in message for message in messages):
        return _parse_role_messages(messages)
    if all("sender" in message for message in messages):
        return _parse_chat_messages(messages)
    raise ValueError("Unsupported message object list format.")


def _parse_text_transcript(text: str) -> list[Turn]:
    """Parse TraceQual markdown or plain-text turn fixtures.

    Walks the text one line at a time. When it sees a header like "Turn 1 (R):"
    it starts a new turn; every line after that (until the next header) is added
    to the current turn's content. This is a common "stateful loop" pattern: the
    `current` variable remembers which turn we're building up.
    """
    turns: list[Turn] = []
    current: Turn | None = None  # the turn we are currently filling in (None at start)

    for raw_line in text.splitlines():  # splitlines() breaks the text into lines
        line = raw_line.strip()
        if not line:
            continue  # ignore blank lines

        # Does this line look like "Turn 3 (R): ..."?
        match = TURN_HEADER_PATTERN.match(line)
        if match:
            # We hit a new header, so the previous turn (if any) is finished.
            if current is not None:
                current["content"] = current["content"].strip()
                turns.append(current)

            # Pull the captured pieces out of the matched header.
            turn_id = int(match.group(1))  # group(1) is the number, as text -> int
            speaker_token = match.group(2).lower()  # group(2) is the role token
            speaker: Speaker = (
                "researcher"
                if speaker_token in {"r", "human", "researcher"}
                else "assistant"
            )
            # Begin a fresh turn; group(3) is any text on the same line as the header.
            current = {
                "turn_id": turn_id,
                "speaker": speaker,
                "content": match.group(3).strip(),
                "timestamp": None,  # plain-text fixtures don't carry timestamps
            }
            continue

        # Not a header: this line is more body text for the turn in progress.
        if current is not None:
            # Add a newline before the new line, unless content is still empty.
            separator = "\n" if current["content"] else ""
            current["content"] = f"{current['content']}{separator}{line}"

    # The loop ends without appending the final turn, so do it here.
    if current is not None:
        current["content"] = current["content"].strip()
        turns.append(current)

    if not turns:
        raise ValueError(
            "No turns found. Expected lines like 'Turn 1 (R): ...' or '**Turn 1 (R):** ...'."
        )
    return turns


def _looks_like_message(message: dict[str, Any]) -> bool:
    """Return True when a dict looks like a single chat message object.

    `any(...)` is True if at least one of these keys is present in the dict.
    """
    return any(key in message for key in ("role", "sender", "text", "content"))


def _extract_message_text(payload: Any) -> str:
    """Normalize string, block list, or nested export content to plain text.

    Message bodies come in several shapes: a plain string, or a list of "blocks"
    (some exports break a message into pieces, e.g. text + images). This collapses
    all of those into one plain string.
    """
    if payload is None:
        return ""  # nothing there
    if isinstance(payload, str):
        return payload  # already plain text
    if isinstance(payload, list):
        # It's a list of blocks; collect the text out of each one.
        parts: list[str] = []
        for block in payload:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                # Blocks store their text under "text" or sometimes "data".
                if block.get("type") == "text":
                    parts.append(str(block.get("text", block.get("data", ""))))
                elif "text" in block:
                    parts.append(str(block["text"]))
                elif "data" in block:
                    parts.append(str(block["data"]))
        # Join the non-empty pieces with newlines into one string.
        return "\n".join(part for part in parts if part)
    return str(payload)  # some other type: best-effort convert to string


def _normalize_timestamp(value: Any) -> str | None:
    """Return an ISO 8601 timestamp string when present, else None."""
    if value is None:
        return None
    timestamp = str(value).strip()
    # `timestamp or None` returns None if the string is empty (empty strings are
    # "falsy" in Python), otherwise the timestamp itself.
    return timestamp or None
