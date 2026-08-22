# Fidelity compare + UX copy

- `BotSpec.ux` holds user-described welcome, menu buttons, contact phone, order statuses.
- `telegram_bot_engine/services/fidelity_compare.py` compares generated bots to the user description and produces repair directives.
- Emitters prefer `ux.menu_buttons` and `ux.welcome` over hardcoded supermarket templates.
- Payment features use PreCheckout / SUCCESSFUL_PAYMENT handlers (not slash commands).
- Creator/content capabilities include commerce schema when market is required.
