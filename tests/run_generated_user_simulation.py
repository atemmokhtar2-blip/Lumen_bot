from __future__ import annotations
import asyncio
import importlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/user_e2e_generated/generated_bot').resolve()
sys.path.insert(0, str(ROOT))
os.environ.pop('TELEGRAM_BOT_TOKEN', None)
for name in list(sys.modules):
    if name == 'app' or name.startswith('app.'):
        del sys.modules[name]
handlers = importlib.import_module('app.handlers')

class User:
    id = 707070
    first_name = 'Ordinary'
    username = 'ordinary_user'
class Chat:
    id = 808080
class Message:
    def __init__(self, text=''):
        self.text = text
        self.message_id = 1
        self.reply_to_message = None
        self.replies = []
    async def reply_text(self, text, **kwargs):
        self.replies.append(str(text))
class Update:
    def __init__(self, text=''):
        self.effective_message = Message(text)
        self.effective_user = User()
        self.effective_chat = Chat()
class Context:
    def __init__(self, args=(), user_data=None):
        self.args = list(args)
        self.user_data = user_data if user_data is not None else {}
        self.chat_data = {}
        self.bot_data = {}

async def call(fn, label, args=(), text=' ', state=None):
    ctx = Context(args, state)
    u = Update(text)
    await fn(u, ctx)
    return label, u.effective_message.replies, ctx.user_data

async def main():
    state = {}
    results = []
    cases = [
        (handlers.start_handler, '/start', (), ''),
        (handlers.help_handler, '/help', (), ''),
        (handlers.handle_lead_capture, '/register', ('Ali','ali@example.com','0100'), ''),
        (handlers.handle_task_add, '/new_task args', ('شراء','خبز'), ''),
        (handlers.handle_task_add, '/new_task prompt', (), ''),
    ]
    for fn, label, args, text in cases:
        lab, replies, state = await call(fn, label, args, text, state)
        results.append({'case': lab, 'replies': replies, 'state': dict(state)})
    # Continue the same conversation after the prompt.
    lab, replies, state = await call(handlers.text_router, 'text after /new_task', (), 'مكالمة العميل', state)
    results.append({'case': lab, 'replies': replies, 'state': dict(state)})
    for fn, label, args, text in [
        (handlers.handle_task_list, '/my_tasks', (), ''),
        (handlers.handle_task_list, '/all_tasks', (), ''),
        (handlers.handle_task_done, '/complete_task bad', ('not-a-number',), ''),
        (handlers.handle_lead_capture, '/new_client', ('شركة','ألف'), ''),
        (handlers.handle_lead_list, '/my_clients', (), ''),
        (handlers.handle_analytics_revenue, '/stats', (), ''),
        (handlers.text_router, 'ordinary text', (), 'مرحبا يا بوت'),
    ]:
        lab, replies, state = await call(fn, label, args, text, state)
        results.append({'case': lab, 'replies': replies, 'state': dict(state)})
    print(json.dumps(results, ensure_ascii=False, indent=2))
    failures = [r for r in results if not r['replies']]
    if failures:
        print('SILENT_CASES=' + json.dumps([r['case'] for r in failures], ensure_ascii=False))
        raise SystemExit(2)
    print('ALL_USER_CASES_REPLIED=1')

asyncio.run(main())
