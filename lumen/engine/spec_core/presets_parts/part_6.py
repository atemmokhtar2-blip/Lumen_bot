def spec_from_request(request: str, *, user_id: int = 0) -> BotSpec | None:
    preset = detect_preset(request)
    if not preset:
        return None
    return session_for_preset(preset, user_id=user_id).to_spec()


__all__ = ["detect_preset", "detect_preset_stack", "score_presets", "compose_session", "session_for_preset", "spec_from_request", "is_bot_request", "default_spec_from_request", "sanitize_spec_for_request"]
