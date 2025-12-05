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
# 1. AccessibilityDatabase — 60 уникальных объектов в Туле (по 20 на тип)
# ===================================================================
class AccessibilityDatabase:
    def __init__(self, db_path: str = "accessibility.db"):
        self.db_path = db_path
        self.init_database()
        self.add_tula_accessibility_all()  # ← 60 объектов!

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
        cursor.execute("""CREATE TABLE IF NOT EXISTS user_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            feature_type TEXT NOT NULL,
            description TEXT,
            address TEXT NOT NULL,
            photo_path TEXT,
            latitude REAL,
            longitude REAL,
            submitted_by TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            must_change_password INTEGER DEFAULT 1
        )""")
        # Insert default admin if not exists
        cursor.execute("SELECT COUNT(*) FROM admins WHERE username = 'admin'")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO admins (username, password, must_change_password) VALUES (?, ?, ?)",
                           ('admin', generate_password_hash('admin'), 1))
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

    def add_user_submission(self, feature_type: str, description: str, address: str, photo_path: str, lat: Optional[float] = None, lon: Optional[float] = None, submitted_by: str = "anonymous"):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""INSERT INTO user_submissions
            (feature_type, description, address, photo_path, latitude, longitude, submitted_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (feature_type, description, address, photo_path, lat, lon, submitted_by))
        conn.commit()
        conn.close()

    def get_pending_submissions(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user_submissions WHERE status = 'pending'")
        rows = cursor.fetchall()
        conn.close()
        return rows

    def approve_submission(self, submission_id: int):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE user_submissions SET status = 'approved' WHERE id = ?", (submission_id,))
        # Move to main table if coordinates are available
        cursor.execute("SELECT feature_type, description, latitude, longitude, address FROM user_submissions WHERE id = ?", (submission_id,))
        row = cursor.fetchone()
        if row and row[2] is not None and row[3] is not None:
            cursor.execute("""INSERT INTO accessibility_objects
                (feature_type, description, latitude, longitude, address)
                VALUES (?, ?, ?, ?, ?)""", row)
        conn.commit()
        conn.close()

    def add_tula_accessibility_all(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM accessibility_objects")
        conn.commit()

        # === 20 объектов ТОЛЬКО для КОЛЯСОЧНИКОВ ===
        wheelchair_objects = [
            ("пандус_стационарный", "Пандус с поручнями", 54.1931, 37.6175, "ТЦ Гостиный двор"),
            ("пандус_стационарный", "Широкий пандус у входа", 54.1965, 37.6140, "Тульский кремль"),
            ("лифт", "Лифт с широкими дверями", 54.1931, 37.6175, "ТЦ Гостиный двор"),
            ("лифт", "Лифт с голосовым оповещением", 54.1920, 37.6200, "Поликлиника №1"),
            ("широкая_дверь", "Автоматические двери 1.4 м", 54.1931, 37.6175, "ТЦ Гостиный двор"),
            ("широкая_дверь", "Двойные двери", 54.1948, 37.6102, "Драмтеатр"),
            ("доступная_парковка", "2 места для маломобильных", 54.1931, 37.6175, "Парковка у Гостиного двора"),
            ("доступная_парковка", "Места у входа", 54.1965, 37.6140, "Тульский кремль"),
            ("пандус_откидной", "Откидной пандус", 54.1910, 37.6250, "ЖД вокзал Тула-1"),
            ("лифт", "Пассажирский лифт", 54.1910, 37.6250, "ЖД вокзал Тула-1"),
            ("широкая_дверь", "Вход без ступеней", 54.2020, 37.6300, "ТЦ Макси"),
            ("пандус_стационарный", "Пандус у аптеки", 54.1890, 37.6180, "ул. Демонстрации"),
            ("доступная_парковка", "Парковка у аптеки", 54.1890, 37.6180, "ул. Демонстрации"),
            ("лифт", "Лифт в подъезде", 54.1950, 37.6150, "ул. Лейтейзена, 10"),
            ("пандус_стационарный", "Пандус у банка", 54.1945, 37.6190, "пр. Ленина, 60"),
            ("широкая_дверь", "Вход в банк", 54.1945, 37.6190, "пр. Ленина, 60"),
            ("доступная_парковка", "Места у банка", 54.1945, 37.6190, "пр. Ленина, 60"),
            ("пандус_стационарный", "Пандус у магазина", 54.1880, 37.6220, "ул. Пузакова"),
            ("лифт", "Лифт в ТЦ", 54.2020, 37.6300, "ТЦ Макси"),
            ("широкая_дверь", "Вход в ТЦ", 54.2020, 37.6300, "ТЦ Макси"),
        ]

        # === 20 объектов ТОЛЬКО для СЛАБОВИДЯЩИХ ===
        visually_impaired_objects = [
            ("тактильная_плитка_направляющая", "Тактильная дорожка", 54.1931, 37.6175, "пр. Ленина → ТЦ"),
            ("тактильная_плитка_направляющая", "Полная разметка", 54.1965, 37.6140, "Тульский кремль"),
            ("светофор_звуковой", "Звуковой сигнал", 54.1928, 37.6168, "пл. Ленина"),
            ("светофор_звуковой", "С таймером", 54.1940, 37.6180, "пр. Ленина / Советская"),
            ("тактильная_плитка_предупреждающая", "Перед переходом", 54.1928, 37.6168, "пл. Ленина"),
            ("тактильная_плитка_предупреждающая", "Перед спуском", 54.1965, 37.6140, "Кремль"),
            ("кнопка_вызова", "Кнопка помощи", 54.1920, 37.6200, "Поликлиника №1"),
            ("кнопка_вызова", "У входа", 54.1910, 37.6250, "ЖД вокзал Тула-1"),
            ("тактильная_плитка_направляющая", "От остановки", 54.1910, 37.6250, "ЖД вокзал Тула-1"),
            ("светофор_звуковой", "На пешеходном переходе", 54.2020, 37.6300, "ул. Октябрьская"),
            ("тактильная_плитка_предупреждающая", "Перед светофором", 54.2020, 37.6300, "ул. Октябрьская"),
            ("тактильная_плитка_направляющая", "Вдоль тротуара", 54.1890, 37.6180, "ул. Демонстрации"),
            ("светофор_звуковой", "С вибросигналом", 54.1950, 37.6150, "ул. Лейтейзена"),
            ("кнопка_вызова", "В подъезде", 54.1950, 37.6150, "ул. Лейтейзена, 10"),
            ("тактильная_плитка_направляющая", "К остановке", 54.1945, 37.6190, "пр. Ленина"),
            ("светофор_звуковой", "У школы", 54.1880, 37.6220, "ул. Пузакова"),
            ("тактильная_плитка_предупреждающая", "Перед школой", 54.1880, 37.6220, "ул. Пузакова"),
            ("тактильная_плитка_направляющая", "К ТЦ", 54.2020, 37.6300, "ТЦ Макси"),
            ("кнопка_вызова", "У входа в ТЦ", 54.2020, 37.6300, "ТЦ Макси"),
            ("светофор_звуковой", "На выезде", 54.2020, 37.6300, "ТЦ Макси"),
        ]

        # === 20 объектов ТОЛЬКО для ОПОРЫ НА ТРОСТЬ ===
        cane_objects = [
            ("поручни", "Двусторонние поручни", 54.1965, 37.6140, "Тульский кремль, лестница"),
            ("поручни", "На входе", 54.1931, 37.6175, "ТЦ Гостиный двор"),
            ("понижение_бордюра", "Плавное понижение", 54.1928, 37.6168, "пл. Ленина"),
            ("понижение_бордюра", "На всех переходах", 54.1940, 37.6180, "пр. Ленина"),
            ("поручни", "В переходе", 54.1910, 37.6250, "ЖД вокзал Тула-1"),
            ("понижение_бордюра", "У вокзала", 54.1910, 37.6250, "ЖД вокзал Тула-1"),
            ("поручни", "На лестнице", 54.2020, 37.6300, "ТЦ Макси"),
            ("понижение_бордюра", "У ТЦ", 54.2020, 37.6300, "ТЦ Макси"),
            ("поручни", "В поликлинике", 54.1920, 37.6200, "Поликлиника №1"),
            ("понижение_бордюра", "У входа", 54.1920, 37.6200, "Поликлиника №1"),
            ("поручни", "На крыльце", 54.1890, 37.6180, "ул. Демонстрации"),
            ("понижение_бордюра", "На тротуаре", 54.1890, 37.6180, "ул. Демонстрации"),
            ("поручни", "В подъезде", 54.1950, 37.6150, "ул. Лейтейзена, 10"),
            ("понижение_бордюра", "У подъезда", 54.1950, 37.6150, "ул. Лейтейзена, 10"),
            ("поручни", "У банка", 54.1945, 37.6190, "пр. Ленина, 60"),
            ("понижение_бордюра", "Перед банком", 54.1945, 37.6190, "пр. Ленина, 60"),
            ("поручни", "У магазина", 54.1880, 37.6220, "ул. Пузакова"),
            ("понижение_бордюра", "У магазина", 54.1880, 37.6220, "ул. Пузакова"),
            ("поручни", "В парке", 54.1900, 37.6100, "Центральный парк"),
            ("понижение_бордюра", "В парке", 54.1900, 37.6100, "Центральный парк"),
        ]

        all_objects = (
            [AccessibilityObject(None, ft, desc, lat, lon, addr) for ft, desc, lat, lon, addr in wheelchair_objects] +
            [AccessibilityObject(None, ft, desc, lat, lon, addr) for ft, desc, lat, lon, addr in visually_impaired_objects] +
            [AccessibilityObject(None, ft, desc, lat, lon, addr) for ft, desc, lat, lon, addr in cane_objects]
        )

        for obj in all_objects:
            self.add_object(obj)

        print(f"УСПЕШНО: добавлено 60 объектов доступности в Туле (по 20 на каждый тип пользователя)!")
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
# AccessibleNavigationSystem — УМНЫЙ маршрут: короткий + приоритет доступности
# ===================================================================
class AccessibleNavigationSystem:
    def __init__(self, db_path: str = "accessibility.db"):
        self.db = AccessibilityDatabase(db_path)
        self.osm = OpenStreetMapAPI()
        # Приоритеты для каждого типа
        self.feature_priorities = {
            MobilityType.WHEELCHAIR: {
                "пандус_стационарный": 10, "лифт": 10, "широкая_дверь": 8,
                "доступная_парковка": 7, "пандус_откидной": 9
            },
            MobilityType.VISUALLY_IMPAIRED: {
                "тактильная_плитка_направляющая": 10, "светофор_звуковой": 10,
                "тактильная_плитка_предупреждающая": 9, "кнопка_вызова": 8
            },
            MobilityType.CANE: {
                "поручни": 10, "понижение_бордюра": 9
            }
        }

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

        # 2. Сначала строим САМЫЙ КОРОТКИЙ маршрут
        base_route_coords, base_data = self.osm.get_route(start_coords, end_coords)
        if not base_route_coords:
            return {"error": "Не удалось построить маршрут"}

        base_distance = base_data["distance"]
        base_duration = int(base_data["duration"] / 60)

        # 3. Ищем объекты доступности ВДОЛЬ маршрута (в радиусе 300 м)
        relevant_features = {
            MobilityType.WHEELCHAIR: ["пандус_стационарный", "лифт", "широкая_дверь", "доступная_парковка", "пандус_откидной"],
            MobilityType.VISUALLY_IMPAIRED: ["тактильная_плитка_направляющая", "светофор_звуковой", "тактильная_плитка_предупреждающая", "кнопка_вызова"],
            MobilityType.CANE: ["поручни", "понижение_бордюра"]
        }.get(mobility_type, [])

        conn = sqlite3.connect("accessibility.db")
        cursor = conn.cursor()
        placeholders = ','.join('?' for _ in relevant_features)

        # Ищем объекты недалеко от любой точки маршрута
        nearby_objects = []
        step = max(1, len(base_route_coords) // 30)
        for i in range(0, len(base_route_coords), step):
            lat, lon = base_route_coords[i]
            cursor.execute(f"""
                SELECT latitude, longitude, feature_type, description, address,
                       (latitude - ?) * (latitude - ?) + (longitude - ?) * (longitude - ?) as dist
                FROM accessibility_objects
                WHERE feature_type IN ({placeholders})
                  AND latitude BETWEEN 54.15 AND 54.25 AND longitude BETWEEN 37.55 AND 37.70
                ORDER BY dist LIMIT 10
            """, [lat, lat, lon, lon] + relevant_features)
            nearby_objects.extend(cursor.fetchall())

        conn.close()

        # Убираем дубликаты
        seen = set()
        unique_objects = []
        for obj in nearby_objects:
            key = (obj[0], obj[1])
            if key not in seen:
                seen.add(key)
                unique_objects.append(obj)

        # 4. Выбираем до 4 лучших объектов (по приоритету + близости к маршруту)
        priorities = self.feature_priorities.get(mobility_type, {})

        def score_object(obj):
            lat, lon, ftype, desc, addr, dist = obj
            priority = priorities.get(ftype, 0)
            distance_penalty = dist * 1000000  # штраф за отклонение
            return priority * 1000 - distance_penalty

        unique_objects.sort(key=score_object, reverse=True)
        best_objects = unique_objects[:4]

        # 5. Строим финальный маршрут: старт → лучшие объекты → финиш
        waypoints = [start_coords]
        used_objects = []

        for obj in best_objects:
            lat, lon, ftype, desc, addr = obj[:5]
            waypoints.append((lat, lon))
            used_objects.append({
                "feature_type": ftype,
                "description": desc,
                "address": addr,
                "latitude": lat,
                "longitude": lon
            })

        waypoints.append(end_coords)

        # Строим маршрут через выбранные объекты
        final_route = []
        total_distance = 0
        total_minutes = 0

        for i in range(len(waypoints) - 1):
            seg_coords, seg_data = self.osm.get_route(waypoints[i], waypoints[i+1])
            if seg_coords and seg_data:
                final_route.extend(seg_coords[:-1])
                total_distance += seg_data["distance"]
                total_minutes += int(seg_data["duration"] / 60)

        final_route.append(waypoints[-1])

        # Если крюк слишком большой — возвращаем короткий маршрут
        if total_distance > base_distance * 1.4:  # не более чем на 40%
            final_route = base_route_coords
            total_distance = base_data["distance"]
            total_minutes = base_duration
            used_objects = []  # но всё равно показываем найденные объекты в описании

        description = self.generate_detailed_description(
            start_addr, end_address, total_distance, total_minutes, used_objects, mobility_type
        )

        return {
            "success": True,
            "start": {"address": start_addr, "coords": start_coords},
            "end": {"address": end_address, "coords": end_coords},
            "route_coords": final_route,
            "accessibility_objects": used_objects,
            "description": description,
            "total_distance": int(total_distance),
            "duration_minutes": total_minutes,
            "mobility_type": mobility_type.value
        }

    def generate_detailed_description(self, start_addr: str, end_addr: str,
                                     distance_m: float, duration_min: int,
                                     objects: List[dict], mobility_type: MobilityType) -> str:
        extra = " (с учётом объектов доступности)" if objects else " (самый короткий)"
        desc = f"""УМНЫЙ МАРШРУТ ДЛЯ {mobility_type.value.upper()}{extra}
{'='*70}
От: {start_addr}
До: {end_addr}

Длина: {int(distance_m)} м | Время в пути: {duration_min} мин

КЛЮЧЕВЫЕ ОБЪЕКТЫ ДОСТУПНОСТИ НА МАРШРУТЕ:
{'='*70}
"""
        if not objects:
            desc += "→ Маршрут оптимален. Объекты доступности поблизости не обнаружены.\n"
        else:
            for i, obj in enumerate(objects, 1):
                name = obj["feature_type"].replace('_', ' ').title()
                desc += f"{i}. {name}\n   {obj['description']}\n   {obj['address']}\n\n"
            desc += "→ Маршрут проходит через эти объекты для вашей безопасности и комфорта!\n"

        desc += "\nБезопасного пути! Вы делаете мир доступнее ♿"
        return desc


# Flask веб-приложение
try:
    from flask import Flask, render_template_string, request, jsonify, redirect, url_for, send_from_directory, session, flash
    from flask_cors import CORS
    from werkzeug.utils import secure_filename
    from werkzeug.security import generate_password_hash, check_password_hash
    import os
    from xml_parser import XMLDataParser

    app = Flask(__name__)
    CORS(app)
    app.secret_key = 'supersecretkey'
    app.config['UPLOAD_FOLDER'] = 'uploads'
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    nav_system = AccessibleNavigationSystem()

    # Load organizations
    parser = XMLDataParser()
    try:
        parser.parse_organizations_xml("xml/Файл_соцподдержка_1.xml")
    except FileNotFoundError:
        print("XML file not found, proceeding without organizations")
    organizations = parser.social_organizations
    
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
            .header .links { margin-top: 20px; }
            .header .links a { color: white; margin: 0 10px; text-decoration: none; }
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
            @media (max-width: 900px) {
                .content {
                    grid-template-columns: 1fr;
                    grid-template-rows: 1fr auto;
                }
                .sidebar {
                    border-right: none;
                    border-bottom: 2px solid #f0f0f0;
                    order: 2;
                }
                #map {
                    order: 1;
                    height: 50vh;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>♿ Доступная навигация</h1>
                <p>Персонализированные маршруты для людей с ограниченными возможностями</p>
                <div class="links">
                    <a href="/submit">Добавить объект</a>
                </div>
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
                            <input type="text" id="endAddress" list="destinations" placeholder="Введите адрес или выберите организацию" required>
                            <datalist id="destinations"></datalist>
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

                        <a href="/submit" class="btn btn-secondary">
                            <span class="icon">➕</span>Добавить объект доступности
                        </a>

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
            // Инициализация MapLibre GL JS — СОВРЕМЕННАЯ КАРТА 2025
            const map = new maplibregl.Map({
                container: 'map',
                style: 'https://tiles.stadiamaps.com/styles/outdoors.json',
                // Альтернатива: стиль от OpenStreetMap France (очень красивый)
                // style: 'https://tiles.stadiamaps.com/styles/osm_bright.json',
                center: [37.6175, 54.1931], // центр Тулы
                zoom: 12,
                pitch: 30,     // лёгкий 3D-наклон
                bearing: 0
            });

            map.addControl(new maplibregl.NavigationControl());
            map.addControl(new maplibregl.GeolocateControl({
                positionOptions: { enableHighAccuracy: true },
                trackUserLocation: true
            }));

            let routeLayer = null;
            let markers = [];
            let userLocation = null;
            let currentRoute = null;

            // Очистка старого маршрута
            function clearRoute() {
                if (routeLayer) {
                    map.removeLayer('route');
                    map.removeSource('route');
                    routeLayer = null;
                }
                markers.forEach(m => m.remove());
                markers = [];
            }

            // Отображение маршрута
            function displayRoute(data) {
                clearRoute();

                const coords = data.route_coords.map(c => [c[1], c[0]]); // [lon, lat]

                // Линия маршрута
                map.addSource('route', {
                    type: 'geojson',
                    data: {
                        type: 'Feature',
                        properties: {},
                        geometry: {
                            type: 'LineString',
                            coordinates: coords
                        }
                    }
                });

                map.addLayer({
                    id: 'route',
                    type: 'line',
                    source: 'route',
                    layout: { 'line-cap': 'round', 'line-join': 'round' },
                    paint: {
                        'line-color': '#667eea',
                        'line-width': 7,
                        'line-opacity': 0.9
                    }
                });

                routeLayer = true;

                // Маркер начала (зелёный)
                new maplibregl.Marker({ color: '#4ade80' })
                    .setLngLat(coords[0])
                    .setPopup(new maplibregl.Popup().setHTML(`<b>Начало</b><br>${data.start.address}`))
                    .addTo(map);

                // Маркер конца (красный)
                new maplibregl.Marker({ color: '#f87171' })
                    .setLngLat(coords[coords.length - 1])
                    .setPopup(new maplibregl.Popup().setHTML(`<b>Финиш</b><br>${data.end.address}`))
                    .addTo(map);

                // Объекты доступности
                const usedPositions = new Set();
                data.accessibility_objects.forEach(obj => {
                    let [lon, lat] = [obj.longitude, obj.latitude];
                    const key = `${lat.toFixed(4)},${lon.toFixed(4)}`;
                    let attempts = 0;
                    while (usedPositions.has(key) && attempts < 10) {
                        lat += (Math.random() - 0.5) * 0.0005; // ~50m jitter
                        lon += (Math.random() - 0.5) * 0.0005;
                        key = `${lat.toFixed(4)},${lon.toFixed(4)}`;
                        attempts++;
                    }
                    usedPositions.add(key);

                    const color = {
                        'пандус_стационарный': '#3b82f6',
                        'лифт': '#8b5cf6',
                        'тактильная_плитка_направляющая': '#f97316',
                        'светофор_звуковой': '#10b981',
                        'поручни': '#a16207',
                        'доступная_парковка': '#06b6d4'
                    }[obj.feature_type] || '#6b7280';

                    new maplibregl.Marker({ color })
                        .setLngLat([lon, lat])
                        .setPopup(new maplibregl.Popup({ offset: 25 }).setHTML(`
                            <b>${obj.feature_type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</b><br>
                            ${obj.description}<br>
                            <small><i>${obj.address}</i></small>
                        `))
                        .addTo(map);
                });

                // Подгоняем камеру
                const bounds = coords.reduce((b, coord) => b.extend(coord), new maplibregl.LngLatBounds(coords[0], coords[0]));
                map.fitBounds(bounds, { padding: 80, duration: 2000 });
            }

            // Геолокация
            document.getElementById('useLocationBtn').addEventListener('click', () => {
                navigator.geolocation.getCurrentPosition(pos => {
                    userLocation = { lat: pos.coords.latitude, lon: pos.coords.longitude };
                    document.getElementById('startAddress').value = 'current';
                    document.getElementById('geoStatus').innerHTML = `Геолокация: ±${pos.coords.accuracy.toFixed(0)} м`;
                    document.getElementById('geoStatus').style.color = 'green';

                    new maplibregl.Marker({ color: '#3b82f6' })
                        .setLngLat([userLocation.lon, userLocation.lat])
                        .setPopup(new maplibregl.Popup().setHTML('<b>Вы здесь</b>'))
                        .addTo(map);
                    map.flyTo({ center: [userLocation.lon, userLocation.lat], zoom: 16 });
                }, err => {
                    document.getElementById('geoStatus').textContent = 'Геолокация недоступна';
                    document.getElementById('geoStatus').style.color = 'red';
                });
            });

            // Построение маршрута
            document.getElementById('routeForm').addEventListener('submit', async e => {
                e.preventDefault();
                clearRoute();

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

            // Озвучка (без изменений)
            document.getElementById('voiceBtn').addEventListener('click', () => {
                if (!currentRoute || !('speechSynthesis' in window)) return;
                speechSynthesis.cancel();
                const texts = [
                    `Маршрут от ${currentRoute.start.address} до ${currentRoute.end.address}`,
                    `Расстояние: ${currentRoute.total_distance} метров. Время в пути: ${currentRoute.duration_minutes} минут`,
                    ...currentRoute.accessibility_objects.slice(0, 6).map(o =>
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

            // Загрузка карты
            map.on('load', () => {
                console.log("MapLibre GL JS загружен — современная карта готова!");
                loadDestinations();
            });

            // Загрузка списка организаций
            async function loadDestinations() {
                try {
                    const res = await fetch('/api/organizations');
                    const orgs = await res.json();
                    const datalist = document.getElementById('destinations');
                    orgs.forEach(org => {
                        const option = document.createElement('option');
                        option.value = org.name + ', ' + org.address;
                        datalist.appendChild(option);
                    });
                } catch (err) {
                    console.error('Failed to load destinations:', err);
                }
            }
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

        # Данные уже добавлены в __init__

        result = nav_system.find_route(
            start_address=start_address,
            end_address=end_address,
            mobility_type=mobility_type,
            user_location=(user_location['lat'], user_location['lon']) if user_location else None
        )

        return jsonify(result)

    @app.route('/api/organizations')
    def api_organizations():
        # Return list of organizations for destination selection
        orgs = [{"name": org.name, "address": org.address, "categories": org.served_disability_categories} for org in organizations[:50]]  # Limit to 50 for UI
        return jsonify(orgs)

    @app.route('/submit')
    def submit_page():
        return render_template_string("""
        <!DOCTYPE html>
        <html lang="ru">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Добавить объект доступности</title>
            <style>
                * { margin: 0; padding: 0; box-sizing: border-box; }
                body {
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    padding: 20px;
                }
                .container {
                    max-width: 800px;
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
                .header .admin-links { margin-top: 20px; }
                .header .admin-links a { color: white; margin: 0 10px; text-decoration: none; }
                .content {
                    padding: 30px;
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
                .form-group input, .form-group select, .form-group textarea {
                    width: 100%;
                    padding: 12px;
                    border: 2px solid #e0e0e0;
                    border-radius: 8px;
                    font-size: 1em;
                    transition: border-color 0.3s;
                }
                .form-group input:focus, .form-group select:focus, .form-group textarea:focus {
                    outline: none;
                    border-color: #667eea;
                }
                #routeForm {
                    display: flex;
                    flex-direction: column;
                    gap: 15px;
                }
                .btn {
                    width: 100%;
                    padding: 15px;
                    border: none;
                    border-radius: 8px;
                    font-size: 1em;
                    font-weight: 600;
                    cursor: pointer;
                    transition: all 0.3s;
                    white-space: nowrap;
                    overflow: hidden;
                    text-overflow: ellipsis;
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
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>♿ Добавить объект доступности</h1>
                    <p>Помогите сделать город доступнее</p>
                </div>
                <div class="content">
                    <form action="/api/submit" method="post" enctype="multipart/form-data">
                        <div class="form-group">
                            <label>Тип объекта:</label>
                            <select name="feature_type" required>
                                <option value="пандус_стационарный">Пандус стационарный</option>
                                <option value="пандус_откидной">Пандус откидной</option>
                                <option value="лифт">Лифт</option>
                                <option value="тактильная_плитка_направляющая">Тактильная плитка направляющая</option>
                                <option value="светофор_звуковой">Звуковой светофор</option>
                                <option value="поручни">Поручни</option>
                                <option value="понижение_бордюра">Понижение бордюра</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Описание:</label>
                            <textarea name="description" required></textarea>
                        </div>
                        <div class="form-group">
                            <label>Адрес:</label>
                            <input type="text" name="address" required>
                        </div>
                        <div class="form-group">
                            <label>Фото:</label>
                            <input type="file" name="photo" accept="image/*" required>
                        </div>
                        <button type="submit" class="btn btn-primary">Отправить на проверку</button>
                        <a href="/" class="btn btn-secondary">Назад</a>
                    </form>
                </div>
            </div>
        </body>
        </html>
        """)

    @app.route('/api/submit', methods=['POST'])
    def api_submit():
        feature_type = request.form['feature_type']
        description = request.form['description']
        address = request.form['address']
        photo = request.files['photo']
        if photo and photo.filename:
            filename = secure_filename(photo.filename)
            photo_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            photo.save(photo_path)
        else:
            photo_path = ""
        nav_system.db.add_user_submission(feature_type, description, address, photo_path)
        return redirect(url_for('submit_page'))

    @app.route('/admin')
    def admin_page():
        submissions = nav_system.db.get_pending_submissions()
        return render_template_string("""
        <!DOCTYPE html>
        <html lang="ru">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Админ панель</title>
            <style>
                * { margin: 0; padding: 0; box-sizing: border-box; }
                body {
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    padding: 20px;
                }
                .container {
                    max-width: 1200px;
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
                    padding: 30px;
                }
                .submission {
                    border: 2px solid #f0f0f0;
                    border-radius: 10px;
                    padding: 20px;
                    margin: 20px 0;
                    background: #fafafa;
                }
                .submission h3 {
                    margin-bottom: 10px;
                    color: #667eea;
                }
                .submission p {
                    margin: 5px 0;
                }
                .submission img {
                    max-width: 300px;
                    margin: 10px 0;
                    border-radius: 8px;
                }
                .btn {
                    padding: 10px 15px;
                    border: none;
                    border-radius: 8px;
                    font-size: 1em;
                    font-weight: 600;
                    cursor: pointer;
                    transition: all 0.3s;
                    margin: 5px;
                }
                .btn-approve {
                    background: #10b981;
                    color: white;
                }
                .btn-approve:hover {
                    background: #059669;
                }
                .btn-reject {
                    background: #ef4444;
                    color: white;
                }
                .btn-reject:hover {
                    background: #dc2626;
                }
                .btn-secondary {
                    background: #f0f0f0;
                    color: #333;
                }
                .btn-secondary:hover {
                    background: #e0e0e0;
                }
                .no-submissions {
                    text-align: center;
                    padding: 50px;
                    color: #666;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🔧 Админ панель</h1>
                    <p>Управление объектами доступности</p>
                    <div class="admin-links">
                        <a href="/admin/change_password">Изменить пароль</a>
                        <a href="/admin/add_admin">Добавить админа</a>
                        <a href="/admin/logout">Выйти</a>
                    </div>
                </div>
                <div class="content">
                    {% if submissions %}
                        {% for sub in submissions %}
                        <div class="submission">
                            <h3>{{ sub[1].replace('_', ' ').title() }}</h3>
                            <p><strong>Описание:</strong> {{ sub[2] }}</p>
                            <p><strong>Адрес:</strong> {{ sub[3] }}</p>
                            <p><strong>Отправитель:</strong> {{ sub[6] or 'Аноним' }}</p>
                            {% if sub[4] %}
                            <img src="/uploads/{{ sub[4].split('/')[-1] }}" alt="Фото объекта">
                            {% endif %}
                            <button class="btn btn-approve" onclick="approve({{ sub[0] }})">✅ Одобрить</button>
                            <button class="btn btn-reject" onclick="reject({{ sub[0] }})">❌ Отклонить</button>
                        </div>
                        {% endfor %}
                    {% else %}
                        <div class="no-submissions">
                            <h2>Нет ожидающих подтверждений</h2>
                            <p>Все объекты проверены</p>
                        </div>
                    {% endif %}
                    <a href="/" class="btn btn-secondary">Назад к навигации</a>
                </div>
            </div>
            <script>
                function approve(id) {
                    fetch('/api/approve/' + id, { method: 'POST' })
                        .then(response => {
                            if (response.ok) {
                                location.reload();
                            } else {
                                alert('Ошибка при одобрении');
                            }
                        });
                }
                function reject(id) {
                    if (confirm('Отклонить объект?')) {
                        fetch('/api/reject/' + id, { method: 'POST' })
                            .then(response => {
                                if (response.ok) {
                                    location.reload();
                                } else {
                                    alert('Ошибка при отклонении');
                                }
                            });
                        }
                    }
            </script>
        </body>
        </html>
        """, submissions=submissions)

    @app.route('/api/approve/<int:submission_id>', methods=['POST'])
    def api_approve(submission_id):
        nav_system.db.approve_submission(submission_id)
        return '', 200

    @app.route('/api/reject/<int:submission_id>', methods=['POST'])
    def api_reject(submission_id):
        try:
            conn = sqlite3.connect("accessibility.db", timeout=10)
            cursor = conn.cursor()
            cursor.execute("UPDATE user_submissions SET status = 'rejected' WHERE id = ?", (submission_id,))
            conn.commit()
        except sqlite3.OperationalError as e:
            return jsonify({"error": "Database locked, try again"}), 500
        finally:
            if 'conn' in locals():
                conn.close()
        return '', 200

    @app.before_request
    def require_admin():
        if request.path.startswith('/admin') and request.path != '/admin/login' and request.path != '/admin/change_password':
            if not session.get('admin'):
                return redirect(url_for('admin_login'))

    @app.route('/admin/login', methods=['GET', 'POST'])
    def admin_login():
        if request.method == 'POST':
            username = request.form['username']
            password = request.form['password']
            conn = sqlite3.connect("accessibility.db")
            cursor = conn.cursor()
            cursor.execute("SELECT password, must_change_password FROM admins WHERE username = ?", (username,))
            row = cursor.fetchone()
            conn.close()
            if row and check_password_hash(row[0], password):
                session['admin'] = username
                if row[1]:
                    return redirect(url_for('change_password'))
                return redirect(url_for('admin_page'))
            flash('Неверные учетные данные')
        return render_template_string("""
        <!DOCTYPE html>
        <html lang="ru">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Вход в админ панель</title>
            <style>
                * { margin: 0; padding: 0; box-sizing: border-box; }
                body {
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }
                .container {
                    background: white;
                    border-radius: 20px;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                    padding: 40px;
                    width: 100%;
                    max-width: 400px;
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
                .form-group input {
                    width: 100%;
                    padding: 12px;
                    border: 2px solid #e0e0e0;
                    border-radius: 8px;
                    font-size: 1em;
                    transition: border-color 0.3s;
                }
                .form-group input:focus {
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
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                }
                .btn:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
                }
                .flash {
                    color: red;
                    margin-bottom: 20px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1 style="text-align: center; margin-bottom: 30px;">Вход в админ панель</h1>
                {% with messages = get_flashed_messages() %}
                    {% if messages %}
                        <div class="flash">{{ messages[0] }}</div>
                    {% endif %}
                {% endwith %}
                <form method="post">
                    <div class="form-group">
                        <label for="username">Имя пользователя:</label>
                        <input type="text" id="username" name="username" required>
                    </div>
                    <div class="form-group">
                        <label for="password">Пароль:</label>
                        <input type="password" id="password" name="password" required>
                    </div>
                    <button type="submit" class="btn">Войти</button>
                </form>
            </div>
        </body>
        </html>
        """)

    @app.route('/admin/change_password', methods=['GET', 'POST'])
    def change_password():
        if not session.get('admin'):
            return redirect(url_for('admin_login'))
        if request.method == 'POST':
            new_password = request.form['new_password']
            confirm_password = request.form['confirm_password']
            if new_password != confirm_password:
                flash('Пароли не совпадают')
                return redirect(request.url)
            conn = sqlite3.connect("accessibility.db")
            cursor = conn.cursor()
            cursor.execute("UPDATE admins SET password = ?, must_change_password = 0 WHERE username = ?",
                           (generate_password_hash(new_password), session['admin']))
            conn.commit()
            conn.close()
            flash('Пароль изменен')
            return redirect(url_for('admin_page'))
        return render_template_string("""
        <!DOCTYPE html>
        <html lang="ru">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Изменить пароль</title>
            <style>
                * { margin: 0; padding: 0; box-sizing: border-box; }
                body {
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }
                .container {
                    background: white;
                    border-radius: 20px;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                    padding: 40px;
                    width: 100%;
                    max-width: 400px;
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
                .form-group input {
                    width: 100%;
                    padding: 12px;
                    border: 2px solid #e0e0e0;
                    border-radius: 8px;
                    font-size: 1em;
                    transition: border-color 0.3s;
                }
                .form-group input:focus {
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
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                }
                .btn:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
                }
                .flash {
                    color: red;
                    margin-bottom: 20px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1 style="text-align: center; margin-bottom: 30px;">Изменить пароль</h1>
                {% with messages = get_flashed_messages() %}
                    {% if messages %}
                        <div class="flash">{{ messages[0] }}</div>
                    {% endif %}
                {% endwith %}
                <form method="post">
                    <div class="form-group">
                        <label for="new_password">Новый пароль:</label>
                        <input type="password" id="new_password" name="new_password" required>
                    </div>
                    <div class="form-group">
                        <label for="confirm_password">Подтвердить пароль:</label>
                        <input type="password" id="confirm_password" name="confirm_password" required>
                    </div>
                    <button type="submit" class="btn">Изменить</button>
                </form>
            </div>
        </body>
        </html>
        """)

    @app.route('/admin/add_admin', methods=['GET', 'POST'])
    def add_admin():
        if not session.get('admin'):
            return redirect(url_for('admin_login'))
        if request.method == 'POST':
            username = request.form['username']
            password = request.form['password']
            conn = sqlite3.connect("accessibility.db")
            cursor = conn.cursor()
            try:
                cursor.execute("INSERT INTO admins (username, password, must_change_password) VALUES (?, ?, ?)",
                               (username, generate_password_hash(password), 0))
                conn.commit()
                flash('Админ добавлен')
            except sqlite3.IntegrityError:
                flash('Имя пользователя уже существует')
            conn.close()
            return redirect(url_for('admin_page'))
        return render_template_string("""
        <!DOCTYPE html>
        <html lang="ru">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Добавить админа</title>
            <style>
                * { margin: 0; padding: 0; box-sizing: border-box; }
                body {
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }
                .container {
                    background: white;
                    border-radius: 20px;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                    padding: 40px;
                    width: 100%;
                    max-width: 400px;
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
                .form-group input {
                    width: 100%;
                    padding: 12px;
                    border: 2px solid #e0e0e0;
                    border-radius: 8px;
                    font-size: 1em;
                    transition: border-color 0.3s;
                }
                .form-group input:focus {
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
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                }
                .btn:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
                }
                .flash {
                    color: red;
                    margin-bottom: 20px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1 style="text-align: center; margin-bottom: 30px;">Добавить админа</h1>
                {% with messages = get_flashed_messages() %}
                    {% if messages %}
                        <div class="flash">{{ messages[0] }}</div>
                    {% endif %}
                {% endwith %}
                <form method="post">
                    <div class="form-group">
                        <label for="username">Имя пользователя:</label>
                        <input type="text" id="username" name="username" required>
                    </div>
                    <div class="form-group">
                        <label for="password">Пароль:</label>
                        <input type="password" id="password" name="password" required>
                    </div>
                    <button type="submit" class="btn">Добавить</button>
                </form>
            </div>
        </body>
        </html>
        """)

    @app.route('/admin/logout')
    def logout():
        session.pop('admin', None)
        return redirect(url_for('admin_login'))

    @app.route('/uploads/<filename>')
    def uploaded_file(filename):
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

    if __name__ == '__main__':
        print("Запуск доступной навигации...")
        print("Откройте в браузере: http://127.0.0.1:5001")
        app.run(debug=True, host='0.0.0.0', port=5000)

except ImportError:
    print("Для запуска веб-интерфейса установите: pip install flask flask-cors requests")
    print("Или запустите только как библиотеку без веб-сервера.")
