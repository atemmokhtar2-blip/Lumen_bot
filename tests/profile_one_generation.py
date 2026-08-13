from __future__ import annotations
import cProfile
import io
import pstats
import shutil
import time
from pathlib import Path

from telegram_bot_engine import generate_bot


def main() -> None:
    out = Path('/tmp/profile_one_generation')
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    request = (
        'اعمل بوت تليجرام لعيادة طبية لحجز المواعيد وإلغاء الحجز وعرض المواعيد. '
        'الأوامر: /start /book /cancel /appointments. يجب أن يرد على الرسائل العادية.'
    )
    profiler = cProfile.Profile()
    started = time.perf_counter()
    profiler.enable()
    result = generate_bot(request, work_dir=out, user_id=990001)
    profiler.disable()
    elapsed = time.perf_counter() - started
    stream = io.StringIO()
    stats = pstats.Stats(profiler, stream=stream).sort_stats('cumulative')
    stats.print_stats(40)
    Path('/tmp/profile_one_generation.txt').write_text(
        f'elapsed_seconds={elapsed:.3f}\n'
        f'result_type={type(result).__name__}\n'
        f'success={getattr(result, "success", None)}\n'
        f'metadata={getattr(result, "metadata", None)}\n\n'
        + stream.getvalue(), encoding='utf-8'
    )
    print(f'elapsed_seconds={elapsed:.3f}')
    print(f'success={getattr(result, "success", None)}')
    print(stream.getvalue())


if __name__ == '__main__':
    main()
