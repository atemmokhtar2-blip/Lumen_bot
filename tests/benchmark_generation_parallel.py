from __future__ import annotations
import shutil
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from lumen.engine import generate_bot

REQUESTS = [
    'بوت عيادة لحجز المواعيد وإلغائها وعرضها.',
    'بوت متجر لعرض المنتجات وتسجيل الطلبات وتتبعها.',
    'بوت تعليم لعرض الدروس والاختبارات وتقدم الطالب.',
    'بوت خدمة عملاء للتذاكر والأولوية والتصعيد.',
    'بوت توصيل لتسجيل الشحنات وتتبع حالة التسليم.',
    'بوت نادي رياضي للتمارين والاشتراكات والحضور.',
    'بوت عقارات لعرض الوحدات وطلبات المعاينة.',
    'بوت مجتمع للنشر والتعليقات والإبلاغ عن المحتوى.',
]


def one(item: tuple[int, str]) -> tuple[int, float, bool]:
    idx, request = item
    out = Path('/tmp/bench_parallel') / f'bot_{idx:02d}'
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    result = generate_bot(request, work_dir=out, user_id=800000 + idx)
    return idx, time.perf_counter() - started, bool(getattr(result, 'success', False))


def main() -> None:
    shutil.rmtree('/tmp/bench_parallel', ignore_errors=True)
    started = time.perf_counter()
    sequential = [one(x) for x in enumerate(REQUESTS, 1)]
    sequential_total = time.perf_counter() - started
    started = time.perf_counter()
    parallel = []
    with ProcessPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(one, x) for x in enumerate(REQUESTS, 1)]
        for future in as_completed(futures):
            parallel.append(future.result())
    parallel_total = time.perf_counter() - started
    print({'sequential_total': round(sequential_total, 3), 'parallel_total': round(parallel_total, 3), 'sequential': sequential, 'parallel': sorted(parallel)})


if __name__ == '__main__':
    main()
