from bot_interface.routers.message_router import _looks_like_generation_request


def main() -> None:
    assert _looks_like_generation_request(
        "عايز اعمل بوت جروب إدارة مجموعات الترحيب بالأعضاء والحظر التلقائي فقط ابدأ"
    ) is True
    assert _looks_like_generation_request("من انت") is False
    assert _looks_like_generation_request("عايز اعمل بوت") is True
    assert _looks_like_generation_request("عايز ترجمة") is False
    print("generation outage fallback classifier: OK")


if __name__ == "__main__":
    main()
