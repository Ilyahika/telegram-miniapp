"""
catalog.py — каталог машин и кейсов. Чистые данные и расчёты, без базы и без FastAPI.
"""
import math

# Названия машин от самой дешёвой к самой дорогой (порядок важен: индекс = «id машины» в БД!)
CAR_NAMES = [
    'ВАЗ-2101 «Копейка»', 'ВАЗ-2105', 'ВАЗ-2106', 'ВАЗ-2107', 'ВАЗ-2109', 'ВАЗ-2110', 'Lada Niva', 'Daewoo Matiz', 'Daewoo Nexia',
    'Lada Kalina', 'Lada Priora', 'Chevrolet Lacetti', 'Lada Granta', 'Lada Vesta', 'Lada XRAY',
    'Kia Rio', 'Hyundai Solaris', 'Renault Logan', 'Skoda Octavia', 'Volkswagen Polo', 'Ford Focus', 'Toyota Corolla', 'Honda Civic',
    'Mazda 3', 'Nissan Qashqai', 'Toyota Camry', 'Mazda 6', 'Kia Optima', 'Hyundai Sonata', 'Subaru Impreza',
    'Volkswagen Passat', 'Skoda Superb', 'Subaru WRX', 'Toyota RAV4', 'Lexus IS', 'BMW 3 Series', 'Audi A4', 'Mercedes C-Class', 'BMW X5', 'Audi Q7',
    'Mercedes E-Class', 'BMW M5', 'Audi RS7', 'Porsche Cayenne', 'Range Rover', 'Mercedes G-Class',
    'Porsche 911', 'Mercedes AMG GT', 'Aston Martin DB11', 'Bentley Continental GT', 'Ferrari F8', 'Lamborghini Huracán', 'McLaren 720S',
    'Lamborghini Aventador', 'Rolls-Royce Phantom', 'Ferrari LaFerrari', 'Pagani Huayra', 'Bugatti Veyron', 'Bugatti Chiron']
N = len(CAR_NAMES)

# Цена растёт геометрической прогрессией: от $400 (Копейка) до ~$3 000 000 (Chiron).
# '%.2g' оставляет 2 значащие цифры, чтобы цены были «круглыми».
CARS = [(name, int(float('%.2g' % (400 * 7500 ** (i / (N - 1)))))) for i, name in enumerate(CAR_NAMES)]


def bonus(value: int) -> int:
    """Прибавка к доходу дома за припаркованную машину, $/час (1% от цены, минимум $1)."""
    return max(1, value // 100)


def car_info(idx: int):
    """Описание машины по индексу или None, если индекс некорректен."""
    if 0 <= idx < N:
        name, value = CARS[idx]
        return {'idx': idx, 'name': name, 'value': value, 'bonus': bonus(value)}
    return None


def _make_case(name: str, lo: int, hi: int, k: float) -> dict:
    """
    Кейс: машины с индексами lo..hi; вес падения экспоненциально убывает с ростом цены (коэффициент k).
    Цена кейса = среднему значению дропа + 12% (так игра в среднем выгодна «казино»).
    """
    weights = {i: math.exp(-k * (i - lo)) for i in range(lo, hi + 1)}
    expected = sum(w * CARS[i][1] for i, w in weights.items()) / sum(weights.values())
    return {'name': name, 'price': int(float('%.2g' % (expected * 1.12))), 'drops': weights}


CASES = {
    'street': _make_case('Улица', 0, 14, .15), 'city': _make_case('Город', 8, 28, .18),
    'biz': _make_case('Бизнес', 20, 40, .2), 'prem': _make_case('Премиум', 32, 50, .22),
    'lux': _make_case('Люкс', 44, 56, .3), 'hyper': _make_case('Гипер', 50, N - 1, .35)}


def _public_cases() -> dict:
    """Описание кейсов для клиента (с шансами в %). Считается один раз при импорте, а не на каждый запрос."""
    out = {}
    for key, case in CASES.items():
        total = sum(case['drops'].values())
        out[key] = {'name': case['name'], 'price': case['price'],
                    'drops': [{'idx': i, 'name': CARS[i][0], 'value': CARS[i][1], 'p': round(w / total * 100, 2)}
                              for i, w in case['drops'].items()]}
    return out


CASES_PUBLIC = _public_cases()
