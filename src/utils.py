import logging
import os
import time

import requests
from openpyxl import load_workbook

from settings import HEADERS, MAX_WAIT_ANSWER

log = logging.getLogger(__name__)


def read_xlsx(fn: str, is_data_only=False):
    if not os.path.isfile(fn):
        logging.error(f'Не найден исходный файл: {fn}')
        return None
    try:
        wb = load_workbook(fn, data_only=is_data_only, )
        return wb
    except Exception as e:
        log.error(f'Ошибка чтения списка из xlsx: {e}')
        return None


def seconds_to_hms(seconds):
    # Конвертация секунд в строку ЧЧ:ММ:СС
    if seconds < 60:
        return f"{seconds:02}sec"

    seconds = int(seconds)
    hours = seconds // 3600
    remainder = seconds % 3600
    minutes = remainder // 60
    secs = remainder % 60
    if hours > 0:
        return f"{hours}h:{minutes:02}m:{secs:02}sec"
    else:
        return f"{minutes}m:{secs:02}sec"


def fetch_page(url: str):
    # Повторная попытка HTTP‑запроса (для чекера WB)
    for try_get in range(1, 6):
        if try_get > 1:
            time.sleep(5)
        try:
            response = requests.get(url, headers=HEADERS, timeout=MAX_WAIT_ANSWER).json()
            if 'По Вашему запросу ничего не найдено' in response:
                logging.info('Ничего на найдено по запросу!')
                return None
            return response
        except Exception as e:
            logging.error(f'Ошибка запроса для ссылки "{url}": {e}')

    return None
