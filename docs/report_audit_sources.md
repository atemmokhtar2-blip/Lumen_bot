# External source note

The Telegram Bot API documentation search result states that standard bot file uploads are limited to 50 MB, while a local Bot API server can support larger uploads. Search result source: https://core.telegram.org/bots/api — Telegram Bot API.

This is used only to justify sending ZIP files below a conservative 45 MB part size when the generated archive exceeds the configured delivery threshold.
