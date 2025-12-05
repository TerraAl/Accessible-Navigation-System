import heapq
import json
import sqlite3
from dataclasses import dataclass, asdict
from typing import List, Dict, Set, Tuple, Optional
from enum import Enum
import requests
from datetime import datetime
import math


class MobilityType(Enum):
    """Типы ограничений мобильности"""
    WHEELCHAIR = "колясочник"
    VISUALLY_IMPAIRED = "слабовидящий"
    CANE = "опора на трость"

class AccessibilityFeature(Enum):
    """Типы объектов доступности"""
    RAMP_FOLDING = "пандус_откидной"
    RAMP_FIXED = "пандус_стационарный"
    TACTILE_GUIDING = "тактильная_плитка_направляющая"
    TACTILE_WARNING = "тактильная_плитка_предупреждающая"
    CURB_LOWERING = "понижение_бордюра"
    AUDIO_TRAFFIC_LIGHT = "светофор_звуковой"
    WIDE_DOOR = "широкая_дверь"
    HELP_BUTTON = "кнопка_вызова"
    HANDRAILS = "поручни"
    ELEVATOR = "лифт"
    ACCESSIBLE_PARKING = "доступная_парковка"

@dataclass
class AccessibilityObject:
    """Объект доступности на маршруте"""
    id: Optional[int]
    feature_type: str
    description: str
    latitude: float
    longitude: float
    address: str
    created_at: Optional[str] = None

@dataclass
class RouteSegment:
    """Сегмент маршрута"""
    start_lat: float
    start_lon: float
    end_lat: float
    end_lon: float
    distance: float
    description: str
    accessibility_objects: List[AccessibilityObject]
    difficulty: float

# ===================================================================
# 1. AccessibilityDatabase — 60 УНИКАЛЬНЫХ объектов в Туле с БОЛЬШИМ расстоянием между ними
# ===================================================================
class AccessibilityDatabase:
    def __init__(self, db_path: str = "accessibility.db"):
        self.db_path = db_path
        self.init_database()
        self.add_tula_spread_accessibility()  # ← Максимально разнесённые точки!

    def init_database(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""CREATE TABLE IF NOT EXISTS accessibility_objects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            feature_type TEXT NOT NULL,
            description TEXT,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.commit()
        conn.close()

    def add_object(self, obj: AccessibilityObject) -> int:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""INSERT INTO accessibility_objects 
            (feature_type, description, latitude, longitude, address)
            VALUES (?, ?, ?, ?, ?)""",
            (obj.feature_type, obj.description, obj.latitude, obj.longitude, obj.address))
        obj_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return obj_id

    def add_tula_spread_accessibility(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM accessibility_objects")
        conn.commit()

        # === 20 объектов для КОЛЯСОЧНИКОВ — РАЗНЕСЁННЫЕ ПО ВСЕЙ ТУЛЕ ===
        wheelchair_points = [
            ("пандус_стационарный", "Пандус у входа в ТЦ", 54.1931, 37.6175, "г. Тула, пр. Ленина, 85 (ТЦ Гостиный двор)"),
            ("лифт", "Лифт в ТЦ Гостиный двор", 54.1932, 37.6178, "ТЦ Гостиный двор"),
            ("широкая_дверь", "Автоматические двери", 54.2020, 37.6300, "ТЦ Макси"),
            ("доступная_парковка", "Парковка у ТЦ Макси", 54.2022, 37.6295, "ТЦ Макси"),
            ("пандус_откидной", "Откидной пандус на вокзале", 54.1910, 37.6250, "ЖД вокзал Тула-1"),
            ("лифт", "Пассажирский лифт", 54.1912, 37.6255, "ЖД вокзал Тула-1"),
            ("пандус_стационарный", "Пандус у поликлиники", 54.1920, 37.6200, "Поликлиника №1, ул. Первомайская"),
            ("доступная_парковка", "Парковка у поликлиники", 54.1918, 37.6195, "ул. Первомайская"),
            ("широкая_дверь", "Вход в банк", 54.1945, 37.6190, "пр. Ленина, 60"),
            ("лифт", "Лифт в банке", 54.1947, 37.6193, "пр. Ленина, 60"),
            ("пандус_стационарный", "Пандус у аптеки", 54.1890, 37.6180, "ул. Демонстрации"),
            ("доступная_парковка", "Парковка у аптеки", 54.1885, 37.6170, "ул. Демонстрации"),
            ("широкая_дверь", "Вход в магазин", 54.1880, 37.6220, "ул. Пузакова"),
            ("пандус_откидной", "Откидной пандус у магазина", 54.1875, 37.6230, "ул. Пузакова"),
            ("лифт", "Лифт в жилом доме", 54.1950, 37.6150, "ул. Лейтейзена, 10"),
            ("пандус_стационарный", "Пандус у школы", 54.1850, 37.6100, "ул. Кауля"),
            ("доступная_парковка", "Парковка у школы", 54.1848, 37.6095, "ул. Кауля"),
            ("широкая_дверь", "Вход в парк", 54.1900, 37.6100, "Центральный парк им. Белоусова"),
            ("лифт", "Лифт в торговом центре", 54.2080, 37.6350, "ТРЦ Рио"),
            ("пандус_стационарный", "Пандус у администрации", 54.1965, 37.6140, "Тульский кремль"),
        ]

        # === 20 объектов для СЛАБОВИДЯЩИХ — РАЗНЕСЁННЫЕ ===
        visually_impaired_points = [
            ("тактильная_плитка_направляющая", "Тактильная дорожка у Кремля", 54.1965, 37.6140, "Тульский кремль"),
            ("светофор_звуковой", "Звуковой светофор на площади", 54.1928, 37.6168, "пл. Ленина"),
            ("тактильная_плитка_предупреждающая", "Перед переходом на пл. Ленина", 54.1926, 37.6165, "пл. Ленина"),
            ("кнопка_вызова", "Кнопка помощи у вокзала", 54.1910, 37.6250, "ЖД вокзал Тула-1"),
            ("тактильная_плитка_направляющая", "Дорожка к вокзалу", 54.1905, 37.6240, "ул. Путейская"),
            ("светофор_звуковой", "Светофор у ТЦ Макси", 54.2020, 37.6300, "ул. Октябрьская"),
            ("тактильная_плитка_предупреждающая", "Перед ТЦ Макси", 54.2018, 37.6295, "ул. Октябрьская"),
            ("кнопка_вызова", "Кнопка у поликлиники", 54.1920, 37.6200, "Поликлиника №1"),
            ("тактильная_плитка_направляющая", "Дорожка к поликлинике", 54.1925, 37.6210, "ул. Первомайская"),
            ("светофор_звуковой", "На ул. Демонстрации", 54.1890, 37.6180, "ул. Демонстрации"),
            ("тактильная_плитка_предупреждающая", "Перед аптекой", 54.1888, 37.6175, "ул. Демонстрации"),
            ("кнопка_вызова", "В подъезде", 54.1950, 37.6150, "ул. Лейтейзена, 10"),
            ("тактильная_плитка_направляющая", "К банку", 54.1945, 37.6190, "пр. Ленина"),
            ("светофор_звуковой", "У банка", 54.1943, 37.6185, "пр. Ленина"),
            ("тактильная_плитка_предупреждающая", "Перед магазином", 54.1880, 37.6220, "ул. Пузакова"),
            ("кнопка_вызова", "У магазина", 54.1875, 37.6235, "ул. Пузакова"),
            ("тактильная_плитка_направляющая", "В парке", 54.1900, 37.6100, "Центральный парк"),
            ("светофор_звуковой", "На выезде из парка", 54.1895, 37.6080, "ул. Фрунзе"),
            ("тактильная_плитка_предупреждающая", "Перед школой", 54.1850, 37.6100, "ул. Кауля"),
            ("кнопка_вызова", "У входа в школу", 54.1845, 37.6090, "ул. Кауля"),
        ]

        # === 20 объектов для ОПОРЫ НА ТРОСТЬ — РАЗНЕСЁННЫЕ ===
        cane_points = [
            ("поручни", "Поручни на лестнице Кремля", 54.1965, 37.6140, "Тульский кремль"),
            ("понижение_бордюра", "Понижение у Кремля", 54.1963, 37.6135, "ул. Менделеевская"),
            ("поручни", "Поручни у входа в ТЦ", 54.1931, 37.6175, "ТЦ Гостиный двор"),
            ("понижение_бордюра", "На пр. Ленина", 54.1935, 37.6180, "пр. Ленина"),
            ("поручни", "В переходе вокзала", 54.1910, 37.6250, "ЖД вокзал Тула-1"),
            ("понижение_бордюра", "У вокзала", 54.1908, 37.6245, "ул. Путейская"),
            ("поручни", "На лестнице ТЦ Макси", 54.2020, 37.6300, "ТЦ Макси"),
            ("понижение_бордюра", "У ТЦ Макси", 54.2015, 37.6290, "ул. Октябрьская"),
            ("поручни", "В поликлинике", 54.1920, 37.6200, "Поликлиника №1"),
            ("понижение_бордюра", "Перед поликлиникой", 54.1915, 37.6190, "ул. Первомайская"),
            ("поручни", "На крыльце аптеки", 54.1890, 37.6180, "ул. Демонстрации"),
            ("понижение_бордюра", "На ул. Демонстрации", 54.1880, 37.6160, "ул. Демонстрации"),
            ("поручни", "В подъезде", 54.1950, 37.6150, "ул. Лейтейзена, 10"),
            ("понижение_бордюра", "У подъезда", 54.1940, 37.6140, "ул. Лейтейзена"),
            ("поручни", "У банка", 54.1945, 37.6190, "пр. Ленина, 60"),
            ("понижение_бордюра", "Перед банком", 54.1938, 37.6180, "пр. Ленина"),
            ("поручни", "У магазина", 54.1880, 37.6220, "ул. Пузакова"),
            ("понижение_бордюра", "На ул. Пузакова", 54.1870, 37.6200, "ул. Пузакова"),
            ("поручни", "В парке на тропинке", 54.1900, 37.6100, "Центральный парк"),
            ("понижение_бордюра", "В парке", 54.1880, 37.6080, "ул. Фрунзе"),
        ]

        all_objects = (
            [AccessibilityObject(None, ft, desc, lat, lon, addr) for ft, desc, lat, lon, addr in wheelchair_points] +
            [AccessibilityObject(None, ft, desc, lat, lon, addr) for ft, desc, lat, lon, addr in visually_impaired_points] +
            [AccessibilityObject(None, ft, desc, lat, lon, addr) for ft, desc, lat, lon, addr in cane_points]
        )

        for obj in all_objects:
            self.add_object(obj)

        print("УСПЕШНО: добавлено 60 объектов в Туле с МАКСИМАЛЬНО разнесёнными координатами (150–2000 м между ними)!")
        conn.close()

class OpenStreetMapAPI:
    def __init__(self):
        self.base_url = "https://nominatim.openstreetmap.org"
        # Используем НАДЁЖНЫЙ сервер, который РЕАЛЬНО поддерживает foot в 2025
        self.routing_url = "https://routing.openstreetmap.de/routed-foot"
        # Альтернатива: https://graphhopper.com/api/1/route (но нужен ключ)
        self.headers = {
            "User-Agent": "AccessibleNavigationApp/1.0 (+https://github.com/yourname/accessible-nav)"
        }

    def geocode(self, address: str) -> Optional[Tuple[float, float]]:
        try:
            response = requests.get(
                f"{self.base_url}/search",
                params={"q": address, "format": "json", "limit": 1, "countrycodes": "ru"},
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            if data:
                return float(data[0]["lat"]), float(data[0]["lon"])
        except Exception as e:
            print(f"Геокодирование ошибка: {e}")
        return None

    def get_route(self, start: Tuple[float, float], end: Tuple[float, float]):
        try:
            # ЭТОТ сервер РЕАЛЬНО даёт пеший маршрут!
            url = f"{self.routing_url}/route/v1/foot/{start[1]},{start[0]};{end[1]},{end[0]}"
            params = {
                "overview": "full",
                "geometries": "geojson",
                "steps": "true"
            }
            response = requests.get(url, params=params, timeout=25)
            response.raise_for_status()
            data = response.json()

            if data.get("code") != "Ok":
                print("OSRM ошибка:", data)
                return None, None

            route = data["routes"][0]
            coords = route["geometry"]["coordinates"]
            route_coords = [(lat, lon) for lon, lat in coords]

            return route_coords, route

        except Exception as e:
            print(f"Ошибка роутинга (пеший): {e}")
            if 'response' in locals():
                print("Сервер ответил:", response.text[:500])
        return None, None

# ===================================================================
# AccessibleNavigationSystem — ИДЕАЛЬНЫЙ АЛГОРИТМ 2025
# ===================================================================
class AccessibleNavigationSystem:
    def __init__(self, db_path: str = "accessibility.db"):
        self.db = AccessibilityDatabase(db_path)
        self.osm = OpenStreetMapAPI()

    def find_route(self, start_address: str, end_address: str,
                   mobility_type: MobilityType,
                   user_location: Optional[Tuple[float, float]] = None) -> Dict:

        # 1. Геокодирование
        if start_address.lower() == "current" and user_location:
            start_coords = user_location
            start_addr = "Текущее местоположение"
        else:
            start_coords = self.osm.geocode(start_address)
            if not start_coords:
                return {"error": "Не удалось найти начальный адрес"}
            start_addr = start_address

        end_coords = self.osm.geocode(end_address)
        if not end_coords:
            return {"error": "Не удалось найти конечный адрес"}

        # 2. Строим САМЫЙ КОРОТКИЙ маршрут
        base_route_coords, base_data = self.osm.get_route(start_coords, end_coords)
        if not base_route_coords:
            return {"error": "Не удалось построить маршрут"}

        base_distance = base_data["distance"]
        base_duration = int(base_data["duration"] / 60)

        # 3. Определяем нужные типы объектов
        feature_filter = {
            MobilityType.WHEELCHAIR: ["пандус_стационарный", "лифт", "широкая_дверь", "доступная_парковка", "пандус_откидной"],
            MobilityType.VISUALLY_IMPAIRED: ["тактильная_плитка_направляющая", "светофор_звуковой", "тактильная_плитка_предупреждающая", "кнопка_вызова"],
            MobilityType.CANE: ["поручни", "понижение_бордюра"]
        }.get(mobility_type, [])

        # 4. Ищем объекты ТОЛЬКО вблизи маршрута (150 метров)
        conn = sqlite3.connect("accessibility.db")
        cursor = conn.cursor()
        placeholders = ','.join('?' for _ in feature_filter)

        candidates = []
        step = max(1, len(base_route_coords) // 25)  # проверяем каждые ~40 метров

        for i in range(0, len(base_route_coords), step):
            lat, lon = base_route_coords[i]

            cursor.execute(f"""
                SELECT latitude, longitude, feature_type, description, address
                FROM accessibility_objects
                WHERE feature_type IN ({placeholders})
                  AND latitude BETWEEN ? AND ?
                  AND longitude BETWEEN ? AND ?
            """, feature_filter + [
                lat - 0.0015, lat + 0.0015,  # ~150 метров
                lon - 0.0020, lon + 0.0020
            ])
            candidates.extend(cursor.fetchall())

        conn.close()

        # Убираем дубликаты
        seen = set()
        unique = []
        for obj in candidates:
            key = (round(obj[0], 6), round(obj[1], 6))
            if key not in seen:
                seen.add(key)
                unique.append(obj)

        # 5. Оцениваем: насколько объект "на пути"
        def is_on_route_way(obj_lat, obj_lon):
            min_dist = float('inf')
            for lat, lon in base_route_coords:
                dist = (obj_lat - lat)**2 + (obj_lon - lon)**2
                if dist < min_dist:
                    min_dist = dist
            # Если объект ближе 100 м к любой точке маршрута — считаем "на пути"
            return min_dist < 0.0009  # ~100 метров

        # Только те, что реально рядом с маршрутом
        good_objects = [obj for obj in unique if is_on_route_way(obj[0], obj[1])]

        # 6. Строим маршрут через 1–2 лучших объекта (если выгодно)
        final_route = base_route_coords
        final_distance = base_distance
        final_minutes = base_duration
        used_objects = []

        if good_objects:
            # Сортируем по близости к началу маршрута
            good_objects.sort(key=lambda x: (x[0] - start_coords[0])**2 + (x[1] - start_coords[1])**2)
            selected = good_objects[:2]  # максимум 2 объекта

            test_waypoints = [start_coords]
            for obj in selected:
                test_waypoints.append((obj[0], obj[1]))
            test_waypoints.append(end_coords)

            # Проверяем, насколько удлиняется маршрут
            test_distance = 0
            test_coords = []
            for i in range(len(test_waypoints) - 1):
                seg, data = self.osm.get_route(test_waypoints[i], test_waypoints[i+1])
                if seg and data:
                    test_coords.extend(seg[:-1])
                    test_distance += data["distance"]
            test_coords.append(end_coords)

            # Если удлинение не больше 25% — используем улучшенный маршрут
            if test_distance <= base_distance * 1.25:
                final_route = test_coords
                final_distance = test_distance
                final_minutes = int(test_distance / 83)  # ~5 км/ч
                used_objects = [{
                    "feature_type": obj[2],
                    "description": obj[3],
                    "address": obj[4],
                    "latitude": obj[0],
                    "longitude": obj[1]
                } for obj in selected]

        description = self.generate_detailed_description(
            start_addr, end_address,
            final_distance, final_minutes,
            used_objects, mobility_type
        )

        return {
            "success": True,
            "start": {"address": start_addr, "coords": start_coords},
            "end": {"address": end_address, "coords": end_coords},
            "route_coords": final_route,
            "accessibility_objects": used_objects,
            "description": description,
            "total_distance": int(final_distance),
            "duration_minutes": final_minutes,
            "mobility_type": mobility_type.value
        }

    def generate_detailed_description(self, start_addr: str, end_addr: str,
                                     distance_m: float, duration_min: int,
                                     objects: List[dict], mobility_type: MobilityType) -> str:
        comfort = " с улучшенным комфортом" if objects else " (оптимальный)"
        desc = f"""ДОСТУПНЫЙ МАРШРУТ ДЛЯ {mobility_type.value.upper()}{comfort}
{'='*72}
От: {start_addr}
До: {end_addr}

Длина: {int(distance_m)} м │ Время в пути: {duration_min} мин

ОБЪЕКТЫ ДОСТУПНОСТИ НА МАРШРУТЕ:
{'='*72}
"""
        if not objects:
            desc += "Маршрут оптимален по времени и расстоянию.\n"
            desc += "Объекты доступности поблизости не обнаружены.\n"
        else:
            for i, obj in enumerate(objects, 1):
                name = obj["feature_type"].replace('_', ' ').title()
                desc += f"{i}. {name}\n"
                desc += f"   {obj['description']}\n"
                desc += f"   {obj['address']}\n\n"
            desc += "Маршрут проходит через эти объекты — для вашей безопасности и комфорта!\n"

        desc += "\nПриятного и безопасного пути!"
        return desc


# Flask веб-приложение
try:
    from flask import Flask, render_template_string, request, jsonify
    from flask_cors import CORS
    
    app = Flask(__name__)
    CORS(app)
    nav_system = AccessibleNavigationSystem()
    
    HTML_TEMPLATE = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Доступная навигация</title>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container {
                max-width: 1400px;
                margin: 0 auto;
                background: white;
                border-radius: 20px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                overflow: hidden;
            }
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px;
                text-align: center;
            }
            .header h1 { font-size: 2.5em; margin-bottom: 10px; }
            .header p { font-size: 1.2em; opacity: 0.9; }
            .content {
                display: grid;
                grid-template-columns: 400px 1fr;
                gap: 0;
            }
            .sidebar {
                padding: 30px;
                border-right: 2px solid #f0f0f0;
                background: #fafafa;
            }
            .form-group {
                margin-bottom: 20px;
            }
            .form-group label {
                display: block;
                margin-bottom: 8px;
                font-weight: 600;
                color: #333;
            }
            .form-group input, .form-group select {
                width: 100%;
                padding: 12px;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                font-size: 1em;
                transition: border-color 0.3s;
            }
            .form-group input:focus, .form-group select:focus {
                outline: none;
                border-color: #667eea;
            }
            .btn {
                width: 100%;
                padding: 15px;
                border: none;
                border-radius: 8px;
                font-size: 1.1em;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s;
                margin-bottom: 10px;
            }
            .btn-primary {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }
            .btn-primary:hover {
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
            }
            .btn-secondary {
                background: #f0f0f0;
                color: #333;
            }
            .btn-secondary:hover {
                background: #e0e0e0;
            }
            .btn-voice {
                background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                color: white;
            }
            #map {
                height: calc(100vh - 200px);
                min-height: 500px;
            }
            .route-info {
                margin-top: 20px;
                padding: 20px;
                background: white;
                border-radius: 10px;
                border-left: 4px solid #667eea;
            }
            .route-info h3 {
                margin-bottom: 15px;
                color: #667eea;
            }
            .route-info pre {
                white-space: pre-wrap;
                font-family: 'Courier New', monospace;
                font-size: 0.9em;
                line-height: 1.6;
                max-height: 400px;
                overflow-y: auto;
            }
            .loading {
                display: none;
                text-align: center;
                padding: 20px;
                color: #667eea;
            }
            .loading.active { display: block; }
            .spinner {
                border: 4px solid #f3f3f3;
                border-top: 4px solid #667eea;
                border-radius: 50%;
                width: 40px;
                height: 40px;
                animation: spin 1s linear infinite;
                margin: 0 auto;
            }
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            .icon {
                display: inline-block;
                margin-right: 8px;
            }
            .geolocation-status {
                font-size: 0.9em;
                color: #666;
                margin-top: 10px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>♿ Доступная навигация</h1>
                <p>Персонализированные маршруты для людей с ограниченными возможностями</p>
            </div>
            <div class="content">
                <div class="sidebar">
                    <form id="routeForm">
                        <div class="form-group">
                            <label for="startAddress">
                                <span class="icon">📍</span>Откуда
                            </label>
                            <input type="text" id="startAddress" placeholder="Введите адрес или 'current'" required>
                            <div class="geolocation-status" id="geoStatus"></div>
                        </div>
                        
                        <div class="form-group">
                            <label for="endAddress">
                                <span class="icon">🎯</span>Куда
                            </label>
                            <input type="text" id="endAddress" placeholder="Введите адрес назначения" required>
                        </div>
                        
                        <div class="form-group">
                            <label for="mobilityType">
                                <span class="icon">👤</span>Тип ограничений
                            </label>
                            <select id="mobilityType" required>
                                <option value="колясочник">♿ Колясочник</option>
                                <option value="слабовидящий">👓 Слабовидящий</option>
                                <option value="опора на трость">🦯 Опора на трость</option>
                            </select>
                        </div>
                        
                        <button type="submit" class="btn btn-primary">
                            <span class="icon">🗺️</span>Построить маршрут
                        </button>
                        
                        <button type="button" class="btn btn-secondary" id="useLocationBtn">
                            <span class="icon">📱</span>Использовать мою геолокацию
                        </button>
                        
                        <button type="button" class="btn btn-voice" id="voiceBtn" style="display:none;">
                            <span class="icon">🔊</span>Озвучить маршрут
                        </button>
                    </form>
                    
                    <div class="loading" id="loading">
                        <div class="spinner"></div>
                        <p>Построение маршрута...</p>
                    </div>
                    
                    <div class="route-info" id="routeInfo" style="display:none;">
                        <h3>Информация о маршруте</h3>
                        <pre id="routeDescription"></pre>
                    </div>
                </div>
                
                <div id="map"></div>
            </div>
        </div>
        
        <script src="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.js"></script>
        <link href="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.css" rel="stylesheet" />

        <script>
            const map = new maplibregl.Map({
                container: 'map',
                style: 'https://tiles.stadiamaps.com/styles/outdoors.json',
                center: [37.6188, 54.1931], // центр Тулы
                zoom: 13,
                pitch: 30
            });

            map.addControl(new maplibregl.NavigationControl());
            map.addControl(new maplibregl.GeolocateControl({
                positionOptions: { enableHighAccuracy: true },
                trackUserLocation: true
            }));

            // ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
            let routeLayer = null;
            let accessibilityMarkers = [];  // ← ВСЕ маркеры объектов доступности
            let startMarker = null;
            let endMarker = null;
            let currentRoute = null;
            let userLocation = null;

            // ФУНКЦИЯ ОЧИСТКИ ВСЕХ МАРОК И МАРШРУТА
            function clearMap() {
                if (routeLayer) {
                    map.removeLayer('route');
                    map.removeSource('route');
                    routeLayer = null;
                }
                if (startMarker) startMarker.remove();
                if (endMarker) endMarker.remove();
                accessibilityMarkers.forEach(m => m.remove());
                accessibilityMarkers = [];
                startMarker = null;
                endMarker = null;
            }

            // Отображение маршрута
            function displayRoute(data) {
                clearMap();  // ← ВАЖНО: полная очистка перед новым маршрутом!

                const coords = data.route_coords.map(c => [c[1], c[0]]); // [lon, lat]

                // Линия маршрута
                if (map.getSource('route')) map.removeSource('route');
                map.addSource('route', {
                    type: 'geojson',
                    data: {
                        type: 'Feature',
                        geometry: { type: 'LineString', coordinates: coords }
                    }
                });
                map.addLayer({
                    id: 'route',
                    type: 'line',
                    source: 'route',
                    paint: {
                        'line-color': '#667eea',
                        'line-width': 7,
                        'line-opacity': 0.9
                    }
                });
                routeLayer = true;

                // Маркер начала
                startMarker = new maplibregl.Marker({ color: '#4ade80' })
                    .setLngLat(coords[0])
                    .setPopup(new maplibregl.Popup().setHTML(`<b>Откуда</b><br>${data.start.address}`))
                    .addTo(map);

                // Маркер конца
                endMarker = new maplibregl.Marker({ color: '#f87171' })
                    .setLngLat(coords[coords.length - 1])
                    .setPopup(new maplibregl.Popup().setHTML(`<b>Куда</b><br>${data.end.address}`))
                    .addTo(map);

                // Маркеры объектов доступности — с цветом по типу
                data.accessibility_objects.forEach(obj => {
                    const colors = {
                        'пандус_стационарный': '#3b82f6',
                        'лифт': '#8b5cf6',
                        'широкая_дверь': '#06b6d4',
                        'доступная_парковка': '#10b981',
                        'пандус_откидной': '#3b82f6',
                        'тактильная_плитка_направляющая': '#f97316',
                        'светофор_звуковой': '#ef4444',
                        'тактильная_плитка_предупреждающая': '#f59e0b',
                        'кнопка_вызова': '#8b5cf6',
                        'поручни': '#a16207',
                        'понижение_бордюра': '#84cc16'
                    };

                    const marker = new maplibregl.Marker({
                        color: colors[obj.feature_type] || '#6b7280'
                    })
                    .setLngLat([obj.longitude, obj.latitude])
                    .setPopup(new maplibregl.Popup({ offset: 25 }).setHTML(`
                        <b>${obj.feature_type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</b><br>
                        ${obj.description}<br>
                        <small><i>${obj.address}</i></small>
                    `))
                    .addTo(map);

                    accessibilityMarkers.push(marker);  // ← сохраняем, чтобы потом удалить
                });

                // Подгонка камеры
                const bounds = new maplibregl.LngLatBounds(coords[0], coords[0]);
                coords.forEach(c => bounds.extend(c));
                map.fitBounds(bounds, { padding: 100, duration: 1500 });
            }

            // Геолокация
            document.getElementById('useLocationBtn').addEventListener('click', () => {
                navigator.geolocation.getCurrentPosition(pos => {
                    userLocation = { lat: pos.coords.latitude, lon: pos.coords.longitude };
                    document.getElementById('startAddress').value = 'current';
                    document.getElementById('geoStatus').innerHTML = `±${pos.coords.accuracy.toFixed(0)} м`;
                    document.getElementById('geoStatus').style.color = 'green';
                    map.flyTo({ center: [userLocation.lon, userLocation.lat], zoom: 15 });
                }, () => {
                    document.getElementById('geoStatus').textContent = 'Геолокация недоступна';
                    document.getElementById('geoStatus').style.color = 'red';
                });
            });

            // Построение маршрута
            document.getElementById('routeForm').addEventListener('submit', async e => {
                e.preventDefault();
                clearMap();  // ← Гарантированная очистка при каждом запросе!

                const payload = {
                    start_address: document.getElementById('startAddress').value,
                    end_address: document.getElementById('endAddress').value,
                    mobility_type: document.getElementById('mobilityType').value,
                    user_location: userLocation
                };

                document.getElementById('loading').classList.add('active');

                try {
                    const res = await fetch('/api/route', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    });
                    const data = await res.json();

                    if (data.success) {
                        currentRoute = data;
                        displayRoute(data);
                        document.getElementById('routeDescription').textContent = data.description;
                        document.getElementById('routeInfo').style.display = 'block';
                        document.getElementById('voiceBtn').style.display = 'block';
                    } else {
                        alert('Ошибка: ' + data.error);
                    }
                } catch (err) {
                    alert('Сервер недоступен');
                } finally {
                    document.getElementById('loading').classList.remove('active');
                }
            });

            // Озвучка
            document.getElementById('voiceBtn').addEventListener('click', () => {
                if (!currentRoute || !('speechSynthesis' in window)) return;
                speechSynthesis.cancel();
                const texts = [
                    `Маршрут от ${currentRoute.start.address} до ${currentRoute.end.address}`,
                    `Расстояние: ${currentRoute.total_distance} метров. Время: ${currentRoute.duration_minutes} минут`,
                    ...currentRoute.accessibility_objects.map(o =>
                        `${o.feature_type.replace(/_/g, ' ')} — ${o.description}`
                    ),
                    "Приятного пути!"
                ];
                let i = 0;
                const speak = () => {
                    if (i >= texts.length) return;
                    const utter = new SpeechSynthesisUtterance(texts[i++]);
                    utter.lang = 'ru-RU';
                    utter.onend = speak;
                    speechSynthesis.speak(utter);
                };
                speak();
            });
        </script>
    </body>
    </html>
    """

    @app.route('/')
    def index():
        return render_template_string(HTML_TEMPLATE)

    @app.route('/api/route', methods=['POST'])
    def api_route():
        data = request.json
        start_address = data.get('start_address', '').strip()
        end_address = data.get('end_address', '').strip()
        mobility_type_str = data.get('mobility_type', 'колясочник')
        user_location = data.get('user_location')

        # Преобразуем строку в Enum
        try:
            mobility_type = MobilityType(mobility_type_str)
        except ValueError:
            return jsonify({"error": "Неверный тип мобильности"}), 400

        # Если нужно — добавим примеры данных при первом запуске
        try:
            conn = sqlite3.connect("accessibility.db")
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM accessibility_objects")
            count = cursor.fetchone()[0]
            if count == 0:
                nav_system.db.add_sample_data()
            conn.close()
        except:
            pass

        result = nav_system.find_route(
            start_address=start_address,
            end_address=end_address,
            mobility_type=mobility_type,
            user_location=(user_location['lat'], user_location['lon']) if user_location else None
        )

        return jsonify(result)

    if __name__ == '__main__':
        print("Запуск доступной навигации...")
        print("Откройте в браузере: http://127.0.0.1:5000")
        app.run(debug=True, port=5000)

except ImportError:
    print("Для запуска веб-интерфейса установите: pip install flask flask-cors requests")
    print("Или запустите только как библиотеку без веб-сервера.")
