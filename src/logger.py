import logging.handlers
from pathlib import Path

# Каталог логов
LOG_DIR = Path(__file__).resolve().parent.parent.joinpath("logs")
Path(LOG_DIR).mkdir(exist_ok=True)


def set_logger():
    # Ротация логов: файл + консоль
    file_log = logging.handlers.RotatingFileHandler(
        filename=LOG_DIR / "app.log",
        mode="a",
        delay=True,
        encoding="utf-8",
        backupCount=5,
        maxBytes=10 * 1024 * 1024,
    )
    file_log.setLevel(logging.INFO)
    console_out = logging.StreamHandler()
    console_out.setLevel(logging.INFO)
    logging.basicConfig(
        handlers=(file_log, console_out),
        format="[%(asctime)s | %(levelname)s]: %(message)s",
        datefmt="%d.%m.%Y %H:%M:%S",
        level=logging.INFO,
    )
