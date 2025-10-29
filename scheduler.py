import asyncio
from datetime import datetime, timezone

UTC = timezone.utc

class Scheduler:
    """
    Minimal in-process scheduler (cron-like).
    Usage:
        sched = Scheduler()
        sched.every(900, coro, arg1, arg2=...)
        await sched.run_forever()
    """
    def __init__(self):
        self.jobs = []  # list[(seconds, coro, args, kwargs, last_run)]

    def every(self, seconds: int, coro, *args, **kwargs):
        self.jobs.append([seconds, coro, args, kwargs, None])

    async def run_forever(self):
        while True:
            now = datetime.now(tz=UTC)
            for job in self.jobs:
                seconds, coro, args, kwargs, last_run = job
                should_run = (last_run is None) or ((now - last_run).total_seconds() >= seconds)
                if should_run:
                    asyncio.create_task(coro(*args, **kwargs))
                    job[4] = now
            await asyncio.sleep(1)
