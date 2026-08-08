"""
SpecTranslator — high-fidelity speech → formal specification JSON with chunking support.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

logger = logging.getLogger("ai_agent_7h_bot.spec_translator")

def chunk_long_text(text: str, max_chunk_size: int = 2000) -> list[str]:
    """
    Split extremely long user texts into logical chunks for mental map processing.
    """
    if len(text) <= max_chunk_size:
        return [text]
    
    paragraphs = text.split("\n")
    chunks: list[str] = []
    current_chunk = ""
    
    for p in paragraphs:
        if len(current_chunk) + len(p) + 1 > max_chunk_size:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = p
        else:
            current_chunk += "\n" + p if current_chunk else p
            
    if current_chunk:
        chunks.append(current_chunk.strip())
        
    return chunks

def merge_spec_json(specs: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Deterministically merge multiple chunk specification JSONs into a single master spec.
    """
    if not specs:
        return {}
    if len(specs) == 1:
        return specs[0]
        
    master = specs[0]
    seen_commands = {c.get("name") for c in master.get("commands", [])}
    seen_entities = {e.get("name") for e in master.get("entities", [])}
    seen_buttons = {b.get("label") for b in master.get("buttons", [])}
    seen_integrations = {i.get("service") for i in master.get("integrations", [])}
    
    for s in specs[1:]:
        for cmd in s.get("commands", []):
            if cmd.get("name") not in seen_commands:
                master.setdefault("commands", []).append(cmd)
                seen_commands.add(cmd.get("name"))
        for ent in s.get("entities", []):
            if ent.get("name") not in seen_entities:
                master.setdefault("entities", []).append(ent)
                seen_entities.add(ent.get("name"))
        for btn in s.get("buttons", []):
            if btn.get("label") not in seen_buttons:
                master.setdefault("buttons", []).append(btn)
                seen_buttons.add(btn.get("label"))
        for integ in s.get("integrations", []):
            if integ.get("service") not in seen_integrations:
                master.setdefault("integrations", []).append(integ)
                seen_integrations.add(integ.get("service"))
                
    return master
