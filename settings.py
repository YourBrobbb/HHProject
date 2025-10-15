# Путь к входному Excel (совместимость с чекером WB)
FN_XLSX = 'Data/ads.xlsx'

# Радиус поиска в WB API
AREA = 40

# Пауза между запросами для чекера WB (сек)
PAUSE_REQUEST = (0.5, 1.)

# Номер колонки с координатами (совместимость с чекером WB)
COLUMN_COORDINATES = 23
# Номер колонки куда писать цвет зоны (совместимость с чекером WB)
COLUMN_COLOR = 26

# Таймаут HTTP‑запросов (сек)
MAX_WAIT_ANSWER = 30
# Базовый User‑Agent для вспомогательных запросов
USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
              'Chrome/134.0.0.0 Safari/537.36')

# Заголовки HTTP по умолчанию
HEADERS = {
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,ko;q=0.6',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'Content-Type': 'application/json, charset=UTF-8',
    'Referer': 'https://google.com',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
    'X-Requested-With': 'XMLHttpRequest',
    'User-Agent': USER_AGENT
}

# Город по умолчанию
CITY_NAME = 'Москва'
# Мин/макс площадь для отбора (м²)
AREA_MIN = 45
AREA_MAX = 200

# Пул реальных User‑Agent для ротации
HEADERS_POOL = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0',
]

# Файлы вывода без зон/с зонами WB
OUTPUT_XLSX = 'Data/ads.xlsx'
OUTPUT_TAGGED_XLSX = 'Data/ads_tagged.xlsx'

# Целевые зоны WB и допуск по расстоянию (м)
WB_ZONES = ["pink", "purple"]
WB_DISTANCE_THRESHOLD_M = 0
# Случайная задержка между запросами (сек)
RANDOM_DELAY_RANGE = (0.8, 2.2)

# Настройки геокодера (контакт обязателен для Nominatim)
GEOCODER_EMAIL = "example@example.com"  # укажите реальную почту
GEOCODER_UA = f"PythonProjectWB/1.0 (contact: {GEOCODER_EMAIL})"
# Прямоугольники города: left,top,right,bottom (lng/lat)
CITY_VIEWBOX = {
    'Москва': (37.3193, 56.0610, 37.9678, 55.4899),  # примерный bbox Москвы
    'Moscow': (37.3193, 56.0610, 37.9678, 55.4899),
    'НАО': (37.05, 55.75, 37.70, 55.30),
    'НАО (Новомосковский)': (37.05, 55.75, 37.70, 55.30),
    'ТАО': (36.70, 55.70, 37.60, 55.10),
    'ТАО (Троицкий)': (36.70, 55.70, 37.60, 55.10),
}

# Порядок колонок в Excel 
COLUMN_ORDER = [
    'source',
    'external_id',
    'url',
    'title',
    'address_raw',
    'address_formatted',
    'city',
    'district',
    'metro',
    'walk_metro_min',
    'lat',
    'lng',
    'area_m2',
    'floor',
    'price_total',
    'price_per_m2',
    'description',
    'seller_type',
    'seller_name',
    'published_at',
    'last_seen_at',
    'status',
    'notes',
]

