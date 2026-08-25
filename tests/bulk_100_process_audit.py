from __future__ import annotations
import json, os, shutil, time, traceback
from concurrent.futures import ProcessPoolExecutor, as_completed, TimeoutError
from pathlib import Path
from bulk_100_user_audit import CASES
from lumen.engine import generate_bot

ROOT = Path('/tmp/bulk_100_process_audit')

def run_case(item):
    idx, (name, desc, commands) = item
    request = f"اعمل بوت تليجرام باسم {name.title()}Hub. {desc}. يجب أن تكون الأوامر التالية واضحة وقابلة للتشغيل: " + ', '.join(commands) + ". يجب أن يرد على أي رسالة عادية برد واضح وألا يتوقف عند خطوة متعددة الرسائل."
    out = ROOT / f'bot_{idx:03d}_{name}'
    shutil.rmtree(out, ignore_errors=True)
    started = time.perf_counter()
    row = {'index': idx, 'name': name, 'request': request, 'commands': commands}
    try:
        result = generate_bot(request, work_dir=out, user_id=910000 + idx)
        meta = getattr(result, 'metadata', {}) or {}
        row.update({'elapsed_s': round(time.perf_counter()-started, 3), 'success': bool(getattr(result, 'success', False)), 'ready_for_token': meta.get('ready_for_token'), 'syntax_ok': meta.get('syntax_ok'), 'errors': meta.get('errors', []), 'files': sum(1 for p in out.rglob('*') if p.is_file())})
    except Exception as exc:
        row.update({'elapsed_s': round(time.perf_counter()-started, 3), 'success': False, 'exception': repr(exc), 'traceback': traceback.format_exc(limit=8)})
    return row

def main():
    shutil.rmtree(ROOT, ignore_errors=True); ROOT.mkdir(parents=True)
    rows=[]; workers=max(1, min(4, int(os.getenv('BULK_PROCESS_WORKERS','4')))); per_case=float(os.getenv('BULK_CASE_TIMEOUT','30'))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(run_case, item): item[0] for item in enumerate(CASES,1)}
        for future in as_completed(futures):
            try: row=future.result(timeout=per_case)
            except TimeoutError: row={'index':futures[future], 'success':False, 'timeout':True}
            except Exception as exc: row={'index':futures[future], 'success':False, 'exception':repr(exc)}
            rows.append(row); print(json.dumps(row,ensure_ascii=False),flush=True)
    rows.sort(key=lambda r:r['index']); (ROOT/'results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    summary={'total':len(rows),'success':sum(bool(r.get('success')) for r in rows),'ready':sum(bool(r.get('ready_for_token')) for r in rows),'syntax_ok':sum(bool(r.get('syntax_ok')) for r in rows),'exceptions':sum('exception' in r for r in rows),'timeouts':sum(bool(r.get('timeout')) for r in rows),'failed':sum(not bool(r.get('success')) for r in rows)}
    (ROOT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8'); print('SUMMARY',json.dumps(summary,ensure_ascii=False)); return 0 if summary['failed']==0 else 2

if __name__=='__main__': raise SystemExit(main())
