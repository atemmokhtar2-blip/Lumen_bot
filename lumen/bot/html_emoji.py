"""Telegram HTML custom emoji (premium) helpers.

Official HTML:
  <tg-emoji emoji-id="ID">FALLBACK</tg-emoji>

Requirements (Bot API 9.4+):
  - Bot owner has Telegram Premium, OR bot has Fragment username
  - parse_mode=HTML
  - Fallback unicode inside the tag is required

IDs are verified public catalog entries (NewsEmoji / TgAndroidIcons / logo packs).
If Telegram rejects an id, the client shows the unicode fallback.
"""
from __future__ import annotations

import os
import re
from typing import Final

# key → (emoji_id, unicode fallback)
# Sources: t.me/addemoji/NewsEmoji, TgAndroidIcons, logo packs (public catalogs)
EMOJI_CATALOG: Final[dict[str, tuple[str, str]]] = {
    # core UI
    "spark": ("5224607267797606837", "⚡"),          # urgent/spark
    "star": ("5438496463044752972", "⭐"),
    "tg_stars": ("5172484558305625218", "⭐"),
    "fire": ("5424972470023104089", "🔥"),
    "check": ("5206607081334906820", "✅"),
    "cross": ("5210952531676504517", "❌"),
    "cancel": ("5240241223632954241", "❌"),
    "question": ("5436113877181941026", "❓"),
    "warning": ("5447644880824181073", "⚠️"),
    "info": ("5323442290708985472", "ℹ️"),
    "refresh": ("5375338737028841420", "🔄"),
    "plus": ("5397916757333654639", "➕"),
    "new": ("5382357040008021292", "🆕"),
    "soon": ("5440621591387980068", "⏳"),
    "free": ("5406756500108501710", "🆓"),
    "link": ("5271604874419647061", "🔗"),
    "lock": ("5296369303661067030", "🔒"),
    "settings": ("5341715473882955310", "⚙️"),
    "download": ("5386367538735104399", "⬇️"),
    "pencil": ("5395444784611480792", "✏️"),
    "idea": ("5422439311196834318", "💡"),
    "bell": ("5458603043203327669", "🔔"),
    "chat": ("5443038326535759644", "💬"),
    "stats": ("5231200819986047254", "📊"),
    "chart_up": ("5449683594425410231", "📈"),
    "dollar": ("5409048419211682843", "💵"),
    "gift": ("5397916757333654639", "🎁"),  # plus as stand-in if no gift; keep dollar nearby
    # packs / bots
    "bot": ("5931415565955503486", "🤖"),
    "wave": ("5870734657384877785", "👋"),
    "wrench": ("5988023995125993550", "🛠"),
    "lab": ("5913787972200698358", "🧪"),
    "eye": ("5960714428394507968", "👁"),
    "wallet": ("5769403330761593044", "👛"),
    "trash": ("5879896690210639947", "🗑"),
    "back": ("5875082500023258804", "↩️"),
    "home": ("5879770735999717115", "🏠"),  # profile as home-ish
    "package": ("5924720918826848520", "📦"),  # layers/package
    "store": ("5983399041197675256", "🏪"),
    "key": ("6005570495603282482", "🔑"),
    "github": ("4999005636604723783", "🐙"),
    "rocket": ("5472169951538224541", "🚀"),  # from catalog (cloud/rocket pack entry)
    "live": ("4927197721900614739", "🔴"),
    "stop": ("5210952531676504517", "⏹"),
    "play": ("5348125953090403204", "▶️"),
}

_TG_EMOJI_RE = re.compile(
    r'<tg-emoji\s+emoji-id="(\d+)">([^<]*)</tg-emoji>',
    re.IGNORECASE,
)

def custom_emoji_enabled() -> bool:
    v = (os.getenv("LUMEN_CUSTOM_EMOJI") or "1").strip().lower()
    return v not in {"0", "false", "no", "off"}


def he(key: str, fallback: str | None = None) -> str:
    """Return official HTML <tg-emoji> or unicode fallback."""
    entry = EMOJI_CATALOG.get(key)
    if not entry:
        return fallback or ""
    eid, fb = entry
    fb = fallback or fb
    if not custom_emoji_enabled():
        return fb
    return f'<tg-emoji emoji-id="{eid}">{fb}</tg-emoji>'


def he_many(*keys: str) -> str:
    return "".join(he(k) for k in keys)


# Protect/restore tg-emoji through html.escape
_PROTECT_OPEN = "\x00TGEMOJI"
_PROTECT_CLOSE = "\x00/TGEMOJI"


def protect_tg_emoji(text: str) -> str:
    """Replace <tg-emoji>...</tg-emoji> with placeholders before escape."""
    if not text or "<tg-emoji" not in text:
        return text
    out: list[str] = []
    last = 0
    for m in _TG_EMOJI_RE.finditer(text):
        out.append(text[last:m.start()])
        out.append(f"{_PROTECT_OPEN}{m.group(1)}|{m.group(2)}{_PROTECT_CLOSE}")
        last = m.end()
    out.append(text[last:])
    return "".join(out)


def restore_tg_emoji(text: str) -> str:
    if not text or _PROTECT_OPEN not in text:
        return text
    def _repl(m: re.Match[str]) -> str:
        eid, fb = m.group(1), m.group(2)
        return f'<tg-emoji emoji-id="{eid}">{fb}</tg-emoji>'
    return re.sub(
        re.escape(_PROTECT_OPEN) + r"(\d+)\|([^\x00]*)" + re.escape(_PROTECT_CLOSE),
        _repl,
        text,
    )


__all__ = [
    "EMOJI_CATALOG",
    "custom_emoji_enabled",
    "he",
    "he_many",
    "protect_tg_emoji",
    "restore_tg_emoji",
]
