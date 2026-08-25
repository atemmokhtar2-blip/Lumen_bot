from __future__ import annotations
import asyncio, importlib, inspect, json, os, sys, traceback
from pathlib import Path

ROOT=Path('/tmp/bulk_100_process_audit')

class User: id=990001; first_name='Bulk'; username='bulk_user'
class Chat: id=990002
class Message:
    def __init__(self,text='مرحبا'):
        self.text=text; self.message_id=1; self.reply_to_message=None; self.replies=[]
    async def reply_text(self,text,**kwargs): self.replies.append(str(text))
class Update:
    def __init__(self,text='مرحبا'):
        self.effective_message=Message(text); self.effective_user=User(); self.effective_chat=Chat()
class Context:
    def __init__(self): self.args=[]; self.user_data={}; self.chat_data={}; self.bot_data={}

async def invoke(fn, name):
    command = name.removeprefix('handle_')
    if command.startswith('explicit_'):
        command = command.removeprefix('explicit_')
    u=Update('/'+command)
    c=Context()
    # Exercise the actual explicit-command business path, not only its prompt.
    if name.startswith('handle_explicit_'):
        c.args=['بيانات', 'اختبار']
    try:
        value=fn(u,c)
        if inspect.isawaitable(value): await asyncio.wait_for(value, timeout=3)
        return {'name':name,'ok':True,'replied':bool(u.effective_message.replies),'replies':u.effective_message.replies[:2]}
    except Exception as e:
        return {'name':name,'ok':False,'replied':False,'error':repr(e),'traceback':traceback.format_exc(limit=3)}

async def one(root):
    env=dict(os.environ); env.pop('TELEGRAM_BOT_TOKEN',None)
    oldpath=list(sys.path); sys.path.insert(0,str(root))
    for n in list(sys.modules):
        if n=='app' or n.startswith('app.'):
            del sys.modules[n]
    out={'root':str(root),'compile_ok':True,'import_ok':False,'handlers':[]}
    try:
        h=importlib.import_module('app.handlers'); importlib.import_module('app.models'); importlib.import_module('app.config')
        out['import_ok']=True
        names=[n for n,v in vars(h).items() if n.startswith('handle_') and callable(v)]
        for n in sorted(names): out['handlers'].append(await invoke(getattr(h,n),n))
        if hasattr(h,'text_router'): out['handlers'].append(await invoke(h.text_router,'text_router'))
    except Exception as e:
        out['import_error']=repr(e); out['traceback']=traceback.format_exc(limit=5)
    finally:
        sys.path[:]=oldpath
    out['handler_errors']=[x for x in out['handlers'] if not x.get('ok')]
    out['silent_handlers']=[x for x in out['handlers'] if x.get('ok') and not x.get('replied')]
    return out

async def main():
    rows=[]
    for wrapper in sorted(ROOT.glob('bot_*')):
        root = wrapper / 'generated_bot'
        rows.append(await one(root))
        print(json.dumps(rows[-1],ensure_ascii=False),flush=True)
    summary={'total':len(rows),'import_ok':sum(r['import_ok'] for r in rows),'handler_error_bots':sum(bool(r['handler_errors']) for r in rows),'silent_bots':sum(bool(r['silent_handlers']) for r in rows),'failed':sum(not r['import_ok'] or bool(r['handler_errors']) for r in rows)}
    (ROOT/'runtime_results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT/'runtime_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print('SUMMARY',json.dumps(summary,ensure_ascii=False))
    raise SystemExit(0 if summary['failed']==0 else 2)
asyncio.run(main())
