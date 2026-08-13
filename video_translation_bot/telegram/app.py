from __future__ import annotations

import asyncio
import logging
import mimetypes
from pathlib import Path
from queue import Queue
from threading import Thread

from ..config.settings import Settings
from ..models import JobRecord, RenderConfiguration, SubtitleConfiguration
from ..pipeline import VideoTranslationPipeline

log = logging.getLogger(__name__)


class TelegramVideoBot:
    def __init__(self, settings: Settings):
        self.settings = settings.ensure()
        self.queue: Queue[tuple[JobRecord, int, SubtitleConfiguration, RenderConfiguration]] = Queue()
        self.jobs: dict[str, JobRecord] = {}
        self.pipeline = VideoTranslationPipeline(settings, progress=self._progress)
        self.application = None
        self.loop = None
        self.worker = Thread(target=self._worker_loop, name="video-translation-worker", daemon=True)
        self.worker.start()

    def _progress(self, job: JobRecord, message: str) -> None:
        log.info("job=%s status=%s progress=%.0f%% %s", job.job_id, job.status.value, job.progress * 100, message)

    def _worker_loop(self) -> None:
        while True:
            job, user_id, subtitle_config, render_config = self.queue.get()
            try:
                output = self.pipeline.process(job, subtitle_config=subtitle_config, render_config=render_config)
                job.metadata["output_path"] = str(output)
                if self.application is not None and self.loop is not None:
                    asyncio.run_coroutine_threadsafe(self._deliver(user_id, output, job), self.loop)
            except Exception:
                log.exception("video job failed: %s", job.job_id)
            finally:
                self.queue.task_done()

    async def _deliver(self, user_id: int, output: Path, job: JobRecord) -> None:
        try:
            with output.open("rb") as handle:
                await self.application.bot.send_video(chat_id=user_id, video=handle, caption=f"تم الانتهاء\nرقم العملية: {job.job_id}")
        except Exception:
            log.exception("Telegram delivery failed for %s", job.job_id)

    async def run(self) -> None:
        if not self.settings.telegram_token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is required to run the Telegram adapter.")
        try:
            from telegram import Update
            from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
        except ImportError as exc:
            raise RuntimeError("Install python-telegram-bot to run the Telegram adapter.") from exc

        application = Application.builder().token(self.settings.telegram_token).build()
        self.application = application
        self.loop = asyncio.get_running_loop()

        async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            await update.message.reply_text("أرسل فيديو أو ملف فيديو، وسأعالج الصوت والترجمة محليًا. لا أستخدم API ذكاء اصطناعي خارجي.")

        async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            user_jobs = [job for job in self.jobs.values() if job.user_id == update.effective_user.id]
            if not user_jobs:
                await update.message.reply_text("لا توجد عمليات مسجلة لهذا المستخدم.")
                return
            latest = user_jobs[-1]
            await update.message.reply_text(f"{latest.job_id}\nالحالة: {latest.status.value}\nالتقدم: {latest.progress:.0%}")

        async def media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            message = update.effective_message
            user_id = update.effective_user.id
            telegram_file = None
            filename = "input.bin"
            mime = None
            if message.video:
                telegram_file = await context.bot.get_file(message.video.file_id)
                filename = message.video.file_name or "input.mp4"
                mime = message.video.mime_type
                file_id = message.video.file_id
                size = message.video.file_size or 0
            elif message.document and (message.document.mime_type or "").startswith(("video/", "audio/")):
                telegram_file = await context.bot.get_file(message.document.file_id)
                filename = message.document.file_name or "input.bin"
                mime = message.document.mime_type
                file_id = message.document.file_id
                size = message.document.file_size or 0
            elif message.audio or message.voice:
                obj = message.audio or message.voice
                telegram_file = await context.bot.get_file(obj.file_id)
                filename = "input.ogg" if message.voice else "input.mp3"
                mime = getattr(obj, "mime_type", None)
                file_id = obj.file_id
                size = obj.file_size or 0
            else:
                return
            if size > self.settings.max_file_size_bytes:
                await message.reply_text("الملف أكبر من الحد المسموح به.")
                return
            job = JobRecord(user_id=user_id, telegram_file_id=file_id, input_type=mime or mimetypes.guess_type(filename)[0] or "unknown", file_size=size, mime_type=mime)
            target = self.settings.data_dir / job.job_id / "incoming" / Path(filename).name
            target.parent.mkdir(parents=True, exist_ok=True)
            await message.reply_text(f"تم استلام الملف. رقم العملية: {job.job_id}\nسيبدأ العمل في الخلفية.")
            await telegram_file.download_to_drive(custom_path=str(target))
            job.input_path = target
            self.jobs[job.job_id] = job
            self.queue.put((job, user_id, SubtitleConfiguration(), RenderConfiguration()))

        async def status_error(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            log.exception("telegram error", exc_info=context.error)

        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("status", status))
        application.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO | filters.AUDIO | filters.VOICE, media))
        application.add_error_handler(status_error)
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        try:
            await asyncio.Event().wait()
        finally:
            await application.updater.stop()
            await application.stop()
            await application.shutdown()
