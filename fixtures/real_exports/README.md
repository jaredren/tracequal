# Real export fixtures (local only)

This directory is used for local parser format checks with real account exports.

## Tested exports (2026-05-28)

Two real exports were tested:

- One Claude account export containing a single synthetic test conversation.
- One ChatGPT account export containing a single synthetic test conversation.

## Results

- Claude export parsed correctly: 8 turns, 4 researcher and 4 assistant, alternating, no malformed text.
- ChatGPT export failed at JSON dispatch with: `ValueError: Unsupported JSON transcript list format.`

## Why ChatGPT failed in v1

The tested ChatGPT export stores messages as a mapping tree keyed by node id, with speaker at `author.role` and text in `content.parts` (a list), plus a hidden system node and a null-message root node. The current parser supports a flat `chat_messages` list with `sender` and `text` fields.

## Privacy and version-control note

Raw export files in this directory are gitignored and are not committed.
