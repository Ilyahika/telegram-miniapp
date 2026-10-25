import math

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
# цена: от $400 (Жигули) до ~$3 000 000 (Bugatti Chiron), геометрическая прогрессия
CARS = [(n, int(float('%.2g' % (400 * 7500 ** (i / (N - 1)))))) for i, n in enumerate(CAR_NAMES)]


def bonus(value):  # прибавка к доходу дома, $/час (1% от цены машины)
    return max(1, value // 100)


def tier(i):  # 0..4 — редкость
    return min(4, i * 5 // N)


def mk_case(name, lo, hi, k):
    w = {i: math.exp(-k * (i - lo)) for i in range(lo, hi + 1)}
    ev = sum(w[i] * CARS[i][1] for i in w) / sum(w.values())
    return {'name': name, 'price': int(float('%.2g' % (ev * 1.12))), 'drops': w}  # цена на ~12% выше средней стоимости дропа


CASES = {'street': mk_case('Улица', 0, 14, .15), 'city': mk_case('Город', 8, 28, .18), 'biz': mk_case('Бизнес', 20, 40, .2),
         'prem': mk_case('Премиум', 32, 50, .22), 'lux': mk_case('Люкс', 44, 56, .3), 'hyper': mk_case('Гипер', 50, N - 1, .35)}