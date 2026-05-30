"""Parse chat transcripts from Claude exports and TraceQual text fixtures."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal, TypedDict

Speaker = Literal["researcher", "assistant"]

TURN_HEADER_PATTERN = re.compile(
    r"^\*{0,2}Turn\s+(\d+)\s+\((R|AI|human|assistant|researcher)\):\*{0,2}\s*(.*)$",
    re.IGNORECASE,
)


class Turn(TypedDict):
    """One turn in a parsed chat transcript."""

    turn_id: int
    speaker: Speaker
    content: str
    timestamp: str | None


def parse_chat(path: Path | str) -> list[Turn]:
    """Parse a chat transcript file into a list of turn dictionaries.

    Format is determined by file extension only (no content sniffing):

    - ``.json``: Claude or API-style JSON exports
    - ``.md``, ``.txt``: TraceQual plain-text or markdown fixtures

    Supports Claude JSON exports (``chat_messages`` or OpenAI-style ``messages``)
    and TraceQual plain-text or markdown fixtures (``Turn N (R): ...`` lines).
    """
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    suffix = file_path.suffix.lower()

    if suffix == ".json":
        return _parse_json_transcript(text)
    if suffix in {".md", ".txt"}:
        if suffix == ".txt" and text.lstrip().startswith("{"):
            raise ValueError(
                "File extension is .txt but content looks like JSON. "
                "Rename to .json or pass format explicitly."
            )
        return _parse_text_transcript(text)

    raise ValueError(
        f"Unsupported file extension {suffix!r}. "
        "Use .json, .md, or .txt."
    )


def format_transcript(turns: list[Turn]) -> str:
    """Format parsed turns for injection into the extraction prompt."""
    blocks: list[str] = []
    for turn in turns:
        label = "R" if turn["speaker"] == "researcher" else "AI"
        blocks.append(f"Turn {turn['turn_id']} ({label}): {turn['content']}")
    return "\n\n".join(blocks)


def _parse_json_transcript(text: str) -> list[Turn]:
    """Parse Claude or API-style JSON chat exports."""
    payload = json.loads(text)
    if isinstance(payload, list):
        if not payload:
            raise ValueError("JSON transcript list is empty.")
        if isinstance(payload[0], dict) and "chat_messages" in payload[0]:
            return _parse_chat_messages(payload[0]["chat_messages"])
        if isinstance(payload[0], dict) and "messages" in payload[0]:
            return _parse_role_messages(payload[0]["messages"])
        if isinstance(payload[0], dict) and _looks_like_message(payload[0]):
            return _parse_message_objects(payload)
        raise ValueError("Unsupported JSON transcript list format.")

    if not isinstance(payload, dict):
        raise ValueError("JSON transcript must be an object or a list of objects.")

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
    for index, message in enumerate(messages, start=1):
        sender = str(message.get("sender", "")).lower()
        if sender in {"human", "user", "researcher", "r"}:
            speaker: Speaker = "researcher"
        elif sender in {"assistant", "ai", "claude"}:
            speaker = "assistant"
        else:
            raise ValueError(f"Unknown sender {sender!r} in chat_messages[{index - 1}].")

        content = _extract_message_text(message.get("text", message.get("content", "")))
        if not content.strip():
            continue

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
    turn_id = 0
    for message in messages:
        role = str(message.get("role", "")).lower()
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

        turn_id += 1
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
        chat_type = str(chat.get("type", "")).lower()
        if chat_type in {"prompt", "human", "user"}:
            speaker: Speaker = "researcher"
        elif chat_type in {"response", "assistant", "ai"}:
            speaker = "assistant"
        else:
            continue

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
    """Parse a bare list of message objects when role fields are present."""
    if all("role" in message for message in messages):
        return _parse_role_messages(messages)
    if all("sender" in message for message in messages):
        return _parse_chat_messages(messages)
    raise ValueError("Unsupported message object list format.")


def _parse_text_transcript(text: str) -> list[Turn]:
    """Parse TraceQual markdown or plain-text turn fixtures."""
    turns: list[Turn] = []
    current: Turn | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        match = TURN_HEADER_PATTERN.match(line)
        if match:
            if current is not None:
                current["content"] = current["content"].strip()
                turns.append(current)

            turn_id = int(match.group(1))
            speaker_token = match.group(2).lower()
            speaker: Speaker = (
                "researcher"
                if speaker_token in {"r", "human", "researcher"}
                else "assistant"
            )
            current = {
                "turn_id": turn_id,
                "speaker": speaker,
                "content": match.group(3).strip(),
                "timestamp": None,
            }
            continue

        if current is not None:
            separator = "\n" if current["content"] else ""
            current["content"] = f"{current['content']}{separator}{line}"

    if current is not None:
        current["content"] = current["content"].strip()
        turns.append(current)

    if not turns:
        raise ValueError(
            "No turns found. Expected lines like 'Turn 1 (R): ...' or '**Turn 1 (R):** ...'."
        )
    return turns


def _looks_like_message(message: dict[str, Any]) -> bool:
    """Return True when a dict looks like a single chat message object."""
    return any(key in message for key in ("role", "sender", "text", "content"))


def _extract_message_text(payload: Any) -> str:
    """Normalize string, block list, or nested export content to plain text."""
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, list):
        parts: list[str] = []
        for block in payload:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(str(block.get("text", block.get("data", ""))))
                elif "text" in block:
                    parts.append(str(block["text"]))
                elif "data" in block:
                    parts.append(str(block["data"]))
        return "\n".join(part for part in parts if part)
    return str(payload)


def _normalize_timestamp(value: Any) -> str | None:
    """Return an ISO 8601 timestamp string when present."""
    if value is None:
        return None
    timestamp = str(value).strip()
    return timestamp or None
