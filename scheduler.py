import logging
import os
import sys

os.environ["DISABLE_SCHEDULER"] = "true"


class SchedulerLogFilter(logging.Filter):
    def filter(self, record):
        message = record.getMessage()
        return "[SCHEDULER_RECAP]" in message or "[DAILY_RECAP]" in message


handler = logging.StreamHandler(sys.stdout)
handler.addFilter(SchedulerLogFilter())
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
root_logger = logging.getLogger()
root_logger.handlers.clear()
root_logger.addHandler(handler)
root_logger.setLevel(logging.INFO)

from app import schedule_surveys


if __name__ == "__main__":
    schedule_surveys()