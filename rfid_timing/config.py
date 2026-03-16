READER_IP = "169.254.1.1"

from sllurp.llrp import LLRP_DEFAULT_PORT
READER_PORT = LLRP_DEFAULT_PORT

# какие антенны считаем финишной аркой
FINISH_ANTENNAS = {1, 2, 3, 4}

# сколько последних событий держим в памяти
MAX_EVENTS = 500

# параметры веб-сервера
WEB_HOST = "0.0.0.0"
WEB_PORT = 8000

# окно сбора считываний одной метки (в секундах)
RSSI_WINDOW_SEC = 2.0

# минимальное время круга (в секундах) - антидребезг
MIN_LAP_TIME_SEC = 120.0