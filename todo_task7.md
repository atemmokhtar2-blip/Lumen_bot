# Task 7: Fix group management bot — commands not working for complex specs

## Root Problem
The engine generates handlers for 57 commands but they're ALL `custom` kind — they just reply with the command name, no actual functionality. The AI translator doesn't understand semantic meaning of commands like /ban, /mute, /lock. The transpiler has no way to generate real action handlers.

## Key Issues
1. AI translator maps all commands to `custom` kind — no semantic understanding
2. Transpiler `custom` handler just replies with command name — no real action
3. No database schema generation from spec table list
4. No ACTION handlers that call Telegram API (ban, mute, kick, pin, delete, etc.)
5. No support for group management features (anti-link, anti-spam, welcome, etc.)
6. No entities/buttons extracted for complex specs

## Plan
- [x] Step 1: Analyze the full scope of what's needed
- [x] Step 2: Add action_type field to RichCommand schema
- [x] Step 3: Enhance AI translator _INFER_SYSTEM prompt — classify action commands, extract entities/tables, set action_type
- [x] Step 4: Enhance transpiler — generate real Telegram API action handlers based on action_type
- [x] Step 5: Add group settings store + warning/filter/rules handlers (covered by action_type handlers) store + warning/filter/rules handlers
- [x] Step 6: Test with the user's exact spec — ALL commands produce functional handlers (test_group_management_actions.py) — verify ALL commands produce functional handlers
- [ ] Step 7: Push to repo
