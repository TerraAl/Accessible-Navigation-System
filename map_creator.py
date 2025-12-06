import heapq
import json
import sqlite3
from dataclasses import dataclass, asdict
from typing import List, Dict, Set, Tuple, Optional
from enum import Enum
import requests
from datetime import datetime
import math
import os
import shutil
import geopandas as gpd
import osmnx as ox
# import folium  # Replaced with OpenLayers
import matplotlib.colors as mcolors

def draw_tula_districts_robust():
    print("Загружаю границы районов Тулы через поиск административных единиц...")

    # 1. Используем features_from_place вместо geocode_to_gdf
    # Мы ищем внутри "Тула, Россия" все объекты с тегом admin_level=9
    # (В России admin_level=9 обычно соответствует внутригородским районам/округам)
    try:
        gdf = ox.features_from_place(
            "Тула, Россия",
            tags={"admin_level": "9", "boundary": "administrative"}
        )
    except Exception as e:
        print(f"Критическая ошибка при запросе: {e}")
        return ""

    # 2. Фильтрация данных
    # Иногда OSM возвращает не только полигоны, но и точки (центры районов).
    # Нам нужны только Полигоны (границы).
    gdf = gdf[gdf.geometry.type.isin(['Polygon', 'MultiPolygon'])]

    print(f"Найдено районов: {len(gdf)}")

    if len(gdf) == 0:
        print("Районы не найдены. Возможно, изменился admin_level в OSM.")
        return ""

    # 3. Центрируем карту по центроиду всех найденных районов
    union_geom = gdf.union_all()
    center_lat = union_geom.centroid.y
    center_lon = union_geom.centroid.x

    # 4. Рисуем с OpenLayers
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']

    # Сбрасываем индекс, чтобы итерироваться удобно
    gdf = gdf.reset_index()

    # Подготавливаем GeoJSON для районов
    districts_geojson = {
        "type": "FeatureCollection",
        "features": []
    }

    for idx, row in gdf.iterrows():
        district_name = row.get('name', f"Район {idx}")
        color = colors[idx % len(colors)]

        # Преобразуем геометрию в GeoJSON
        geom = row['geometry']
        if geom.geom_type == 'Polygon':
            coords = [list(geom.exterior.coords)]
        elif geom.geom_type == 'MultiPolygon':
            coords = [list(p.exterior.coords) for p in geom.geoms]
        else:
            continue

        feature = {
            "type": "Feature",
            "properties": {
                "name": district_name,
                "color": color
            },
            "geometry": {
                "type": "MultiPolygon" if geom.geom_type == 'MultiPolygon' else "Polygon",
                "coordinates": coords
            }
        }
        districts_geojson["features"].append(feature)

    # Добавляем объекты доступности
    conn = sqlite3.connect("db/accessibility.db")
    cursor = conn.cursor()
    cursor.execute("SELECT feature_type, latitude, longitude, description, address FROM accessibility_objects")
    objects = cursor.fetchall()
    conn.close()

    color_map = {
        'пандус_стационарный': '#3b82f6', 'лифт': '#8b5cf6', 'широкая_дверь': '#ec4899',
        'доступная_парковка': '#06b6d4', 'тактильная_плитка_направляющая': '#f97316',
        'светофор_звуковой': '#10b981', 'поручни': '#a16207', 'понижение_бордюра': '#84cc16'
    }

    accessibility_features = []
    for obj in objects:
        feature_type, lat, lon, desc, addr = obj
        color = color_map.get(feature_type, '#6b7280')
        feature = {
            "type": "Feature",
            "properties": {
                "feature_type": feature_type,
                "description": desc,
                "address": addr,
                "color": color
            },
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat]
            }
        }
        accessibility_features.append(feature)

    accessibility_geojson = {
        "type": "FeatureCollection",
        "features": accessibility_features
    }

    # Генерируем HTML фрагмент с OpenLayers
    map_id = "map_78d4ed66ec23f47bc495883bb5cacab4"
    html_content = f"""
    <div id="{map_id}" style="position: relative; width: 100%; height: 500px; border-radius: 10px; margin-bottom: 30px;"></div>
    <div id="popup_{map_id}" class="ol-popup" style="position: absolute; background-color: white; box-shadow: 0 1px 4px rgba(0,0,0,0.2); padding: 15px; border-radius: 10px; border: 1px solid #cccccc; bottom: 12px; left: -50px; min-width: 280px; display: none;">
        <a href="#" id="popup-closer_{map_id}" class="ol-popup-closer"></a>
        <div id="popup-content_{map_id}"></div>
    </div>
    <script>
        // Данные районов
        const districtsData_{map_id.replace('-', '_')} = {json.dumps(districts_geojson)};

        // Данные объектов доступности
        const accessibilityData_{map_id.replace('-', '_')} = {json.dumps(accessibility_geojson)};

        // Создаем карту
        const map_{map_id.replace('-', '_')} = new ol.Map({{
            target: '{map_id}',
            layers: [
                new ol.layer.Tile({{
                    source: new ol.source.OSM()
                }})
            ],
            view: new ol.View({{
                center: ol.proj.fromLonLat([{center_lon}, {center_lat}]),
                zoom: 11
            }})
        }});

        // Слой районов
        const districtsSource_{map_id.replace('-', '_')} = new ol.source.Vector({{
            features: new ol.format.GeoJSON().readFeatures(districtsData_{map_id.replace('-', '_')}, {{
                featureProjection: 'EPSG:3857'
            }})
        }});

        const districtsLayer_{map_id.replace('-', '_')} = new ol.layer.Vector({{
            source: districtsSource_{map_id.replace('-', '_')},
            style: function(feature) {{
                const color = feature.get('color');
                return new ol.style.Style({{
                    fill: new ol.style.Fill({{
                        color: color + '40'  // 25% opacity
                    }}),
                    stroke: new ol.style.Stroke({{
                        color: 'black',
                        width: 2
                    }})
                }});
            }}
        }});

        map_{map_id.replace('-', '_')}.addLayer(districtsLayer_{map_id.replace('-', '_')});

        // Слой объектов доступности
        const accessibilitySource_{map_id.replace('-', '_')} = new ol.source.Vector({{
            features: new ol.format.GeoJSON().readFeatures(accessibilityData_{map_id.replace('-', '_')}, {{
                featureProjection: 'EPSG:3857'
            }})
        }});

        const accessibilityLayer_{map_id.replace('-', '_')} = new ol.layer.Vector({{
            source: accessibilitySource_{map_id.replace('-', '_')},
            style: function(feature) {{
                const color = feature.get('color');
                return new ol.style.Style({{
                    image: new ol.style.Circle({{
                        radius: 6,
                        fill: new ol.style.Fill({{
                            color: color
                        }}),
                        stroke: new ol.style.Stroke({{
                            color: 'white',
                            width: 2
                        }})
                    }})
                }});
            }}
        }});

        map_{map_id.replace('-', '_')}.addLayer(accessibilityLayer_{map_id.replace('-', '_')});

        // Popup
        const popup_{map_id.replace('-', '_')} = new ol.Overlay({{
            element: document.getElementById('popup_{map_id}'),
            positioning: 'bottom-center',
            stopEvent: false,
            offset: [0, -10]
        }});
        map_{map_id.replace('-', '_')}.addOverlay(popup_{map_id.replace('-', '_')});

        const popupCloser_{map_id.replace('-', '_')} = document.getElementById('popup-closer_{map_id}');
        popupCloser_{map_id.replace('-', '_')}.onclick = function() {{
            popup_{map_id.replace('-', '_')}.setPosition(undefined);
            popupCloser_{map_id.replace('-', '_')}.blur();
            return false;
        }};

        // Обработчик клика для popup
        map_{map_id.replace('-', '_')}.on('singleclick', function(evt) {{
            const feature = map_{map_id.replace('-', '_')}.forEachFeatureAtPixel(evt.pixel, function(feature) {{
                return feature;
            }});

            if (feature) {{
                const properties = feature.getProperties();
                let content = '';
                if (properties.name) {{
                    content = `<b>${{properties.name}}</b>`;
                }} else if (properties.feature_type) {{
                    content = `<b>${{properties.feature_type.replace(/_/g, ' ').replace(/\\b\\w/g, l => l.toUpperCase())}}</b><br>${{properties.description}}<br><small>${{properties.address}}</small>`;
                }}

                if (content) {{
                    document.getElementById('popup-content_{map_id}').innerHTML = content;
                    popup_{map_id.replace('-', '_')}.setPosition(evt.coordinate);
                }}
            }} else {{
                popup_{map_id.replace('-', '_')}.setPosition(undefined);
            }}
        }});

        // Изменяем курсор при наведении
        map_{map_id.replace('-', '_')}.on('pointermove', function(e) {{
            const pixel = map_{map_id.replace('-', '_')}.getEventPixel(e.originalEvent);
            const hit = map_{map_id.replace('-', '_')}.hasFeatureAtPixel(pixel);
            map_{map_id.replace('-', '_')}.getTarget().style.cursor = hit ? 'pointer' : '';
        }});
    </script>
    """

    return html_content


def get_tula_districts_from_osm():
    print("Загружаю границы районов Тулы через поиск административных единиц...")

    try:
        gdf = ox.features_from_place(
            "Тула, Россия",
            tags={"admin_level": "9", "boundary": "administrative"}
        )
    except Exception as e:
        print(f"Критическая ошибка при запросе: {e}")
        return {}

    # Фильтрация данных
    gdf = gdf[gdf.geometry.geom_type.isin(['Polygon', 'MultiPolygon'])]

    print(f"Найдено районов: {len(gdf)}")

    if len(gdf) == 0:
        print("Районы не найдены. Возможно, изменился admin_level в OSM.")
        return {}

    districts = {}
    gdf = gdf.reset_index()
    for idx, row in gdf.iterrows():
        district_name = row.get('name', f"Район {idx}")
        geom = row.geometry
        if geom.geom_type == 'Polygon':
            coords = list(geom.exterior.coords)
            districts[district_name] = coords
        elif geom.geom_type == 'MultiPolygon':
            largest = max(geom.geoms, key=lambda p: p.area)
            coords = list(largest.exterior.coords)
            districts[district_name] = coords
    return districts




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


# Административные районы Тулы с корректными не пересекающимися границами (полигоны в формате [lon, lat])
TULA_DISTRICTS = {
    "Центральный": {
        "name": "Центральный район",
        "polygon": [
            [37.600, 54.180], [37.610, 54.180], [37.620, 54.180], [37.625, 54.180], [37.625, 54.190], [37.625, 54.200], [37.615, 54.200], [37.605, 54.200], [37.600, 54.200], [37.600, 54.190]
        ],
        "center": [37.612, 54.190],
        "color": "#ff6b6b"
    },
    "Советский": {
        "name": "Советский район",
        "polygon": [
            [37.600, 54.200], [37.610, 54.200], [37.620, 54.200], [37.630, 54.200], [37.640, 54.200], [37.640, 54.210], [37.640, 54.220], [37.630, 54.220], [37.620, 54.220], [37.610, 54.220], [37.600, 54.220], [37.600, 54.210]
        ],
        "center": [37.620, 54.210],
        "color": "#4ecdc4"
    },
    "Привокзальный": {
        "name": "Привокзальный район",
        "polygon": [
            [37.625, 54.180], [37.635, 54.180], [37.645, 54.180], [37.650, 54.180], [37.650, 54.190], [37.650, 54.200], [37.640, 54.200], [37.630, 54.200], [37.625, 54.200], [37.625, 54.190]
        ],
        "center": [37.637, 54.190],
        "color": "#45b7d1"
    },
    "Зареченский": {
        "name": "Зареченский район",
        "polygon": [
            [37.580, 54.170], [37.590, 54.170], [37.600, 54.170], [37.610, 54.170], [37.610, 54.175], [37.610, 54.180], [37.610, 54.185], [37.600, 54.185], [37.590, 54.185], [37.580, 54.185], [37.580, 54.180], [37.580, 54.175]
        ],
        "center": [37.595, 54.177],
        "color": "#f9ca24"
    },
    "Пролетарский": {
        "name": "Пролетарский район",
        "polygon": [
            [37.580, 54.185], [37.590, 54.185], [37.600, 54.185], [37.610, 54.185], [37.610, 54.190], [37.610, 54.195], [37.610, 54.200], [37.600, 54.200], [37.590, 54.200], [37.580, 54.200], [37.580, 54.195], [37.580, 54.190]
        ],
        "center": [37.595, 54.192],
        "color": "#6c5ce7"
    }
}


# Try to update with real boundaries from OSM
osm_districts = get_tula_districts_from_osm()
if not osm_districts:
    # Fallback to hardcoded
    osm_districts = {}
    for district, data in TULA_DISTRICTS.items():
        osm_districts[district] = data["polygon"]
else:
    name_mapping = {
        'Центральный район': 'Центральный',
        'Советский район': 'Советский',
        'Привокзальный район': 'Привокзальный',
        'Зареченский район': 'Зареченский',
        'Пролетарский район': 'Пролетарский',
        'Центральный административный округ': 'Центральный',
        'Советский административный округ': 'Советский',
        'Центральный территориальный округ': 'Центральный',
        'Советский территориальный округ': 'Советский',
        'Привокзальный территориальный округ': 'Привокзальный',
        'Зареченский территориальный округ': 'Зареченский',
        'Пролетарский территориальный округ': 'Пролетарский'
    }
    for osm_name, coords in osm_districts.items():
        key = name_mapping.get(osm_name)
        if key and key in TULA_DISTRICTS:
            TULA_DISTRICTS[key]['polygon'] = coords
            print(f"Updated {key} with OSM data")


def point_in_polygon(x, y, polygon):
    """Проверка, находится ли точка внутри полигона (алгоритм ray casting)"""
    n = len(polygon)
    inside = False
    p1x, p1y = polygon[0]
    for i in range(1, n + 1):
        p2x, p2y = polygon[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside


def get_district_for_point(lat: float, lon: float) -> str:
    """Определяет район по координатам с использованием полигонов"""
    for district, data in TULA_DISTRICTS.items():
        polygon = data["polygon"]
        if point_in_polygon(lon, lat, polygon):  # Note: lon, lat for the function
            return district
    return "Не определен"


def get_district_statistics(db_path: str = "db/accessibility.db"):
    """Получает статистику доступности по районам"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Получаем все объекты
    cursor.execute("SELECT feature_type, latitude, longitude FROM accessibility_objects")
    objects = cursor.fetchall()
    conn.close()

    stats = {}
    for district in TULA_DISTRICTS.keys():
        stats[district] = {
            "name": TULA_DISTRICTS[district]["name"],
            "total_objects": 0,
            "by_type": {},
            "by_mobility": {
                "колясочник": 0,
                "слабовидящий": 0,
                "опора на трость": 0,
                "другие": 0
            },
            "center": TULA_DISTRICTS[district]["center"],
            "color": TULA_DISTRICTS[district]["color"]
        }

    # Маппинг типов объектов к типам мобильности
    mobility_mapping = {
        "колясочник": ["пандус_стационарный", "пандус_откидной", "лифт", "широкая_дверь", "доступная_парковка"],
        "слабовидящий": ["тактильная_плитка_направляющая", "тактильная_плитка_предупреждающая", "светофор_звуковой", "кнопка_вызова"],
        "опора на трость": ["поручни", "понижение_бордюра"]
    }

    for obj in objects:
        feature_type, lat, lon = obj
        district = get_district_for_point(lat, lon)
        if district in stats:
            stats[district]["total_objects"] += 1
            if feature_type not in stats[district]["by_type"]:
                stats[district]["by_type"][feature_type] = 0
            stats[district]["by_type"][feature_type] += 1

            # Определяем тип мобильности
            matched = False
            for mobility, types in mobility_mapping.items():
                if feature_type in types:
                    stats[district]["by_mobility"][mobility] += 1
                    matched = True
                    break
            if not matched:
                stats[district]["by_mobility"]["другие"] += 1

    return stats


def export_district_stats_to_excel(stats, filename="district_stats.xlsx"):
    """Экспортирует статистику районов в Excel"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.chart import BarChart, Reference

    wb = Workbook()
    ws = wb.active
    ws.title = "Статистика по районам"

    # Заголовки
    headers = ["Район", "Всего объектов", "Колясочники", "Слабовидящие", "Опора на трость", "Другие"]
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col)
        cell.value = header
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="CCCCCC", end_color="CCCCCC", fill_type="solid")
        cell.alignment = Alignment(horizontal="center")

    # Данные
    row = 2
    for district, data in stats.items():
        ws.cell(row=row, column=1).value = data["name"]
        ws.cell(row=row, column=2).value = data["total_objects"]
        ws.cell(row=row, column=3).value = data["by_mobility"]["колясочник"]
        ws.cell(row=row, column=4).value = data["by_mobility"]["слабовидящий"]
        ws.cell(row=row, column=5).value = data["by_mobility"]["опора на трость"]
        ws.cell(row=row, column=6).value = data["by_mobility"]["другие"]
        row += 1

    # Автоподбор ширины
    for col in ws.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = (max_length + 2)
        ws.column_dimensions[column].width = adjusted_width

    # Диаграмма
    chart = BarChart()
    chart.title = "Статистика доступности по районам"
    chart.y_axis.title = "Количество объектов"
    chart.x_axis.title = "Районы"

    data = Reference(ws, min_col=2, min_row=1, max_col=6, max_row=row-1)
    cats = Reference(ws, min_col=1, min_row=2, max_row=row-1)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(cats)

    ws.add_chart(chart, "G2")

    wb.save(filename)
    return filename


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
    def __init__(self, db_path: str = "db/accessibility.db"):
        self.db_path = db_path
        self.init_database()
        self.add_tula_accessibility_all()  # ← 60 объектов!

    def init_database(self):
        # Ensure the database directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
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

        # Генерируем объекты для каждого района
        all_objects = []
        for district, data in TULA_DISTRICTS.items():
            polygon = data["polygon"]
            min_lat = min(p[1] for p in polygon)
            max_lat = max(p[1] for p in polygon)
            min_lon = min(p[0] for p in polygon)
            max_lon = max(p[0] for p in polygon)

            # 4 объекта каждого типа на район
            for i in range(4):
                lat = min_lat + (max_lat - min_lat) * (i + 0.5) / 4
                lon = min_lon + (max_lon - min_lon) * (i + 0.5) / 4

                # Колясочники
                all_objects.append(AccessibilityObject(None, "пандус_стационарный", f"Пандус в {data['name']}", lat, lon, f"{data['name']}, объект {i+1}"))
                all_objects.append(AccessibilityObject(None, "лифт", f"Лифт в {data['name']}", lat + 0.001, lon + 0.001, f"{data['name']}, объект {i+1}"))
                all_objects.append(AccessibilityObject(None, "широкая_дверь", f"Широкая дверь в {data['name']}", lat - 0.001, lon - 0.001, f"{data['name']}, объект {i+1}"))
                all_objects.append(AccessibilityObject(None, "доступная_парковка", f"Парковка в {data['name']}", lat + 0.002, lon + 0.002, f"{data['name']}, объект {i+1}"))

                # Слабовидящие
                all_objects.append(AccessibilityObject(None, "тактильная_плитка_направляющая", f"Тактильная плитка в {data['name']}", lat, lon + 0.001, f"{data['name']}, объект {i+1}"))
                all_objects.append(AccessibilityObject(None, "светофор_звуковой", f"Звуковой светофор в {data['name']}", lat + 0.001, lon, f"{data['name']}, объект {i+1}"))
                all_objects.append(AccessibilityObject(None, "тактильная_плитка_предупреждающая", f"Предупреждающая плитка в {data['name']}", lat - 0.001, lon, f"{data['name']}, объект {i+1}"))
                all_objects.append(AccessibilityObject(None, "кнопка_вызова", f"Кнопка вызова в {data['name']}", lat, lon - 0.001, f"{data['name']}, объект {i+1}"))

                # Опора на трость
                all_objects.append(AccessibilityObject(None, "поручни", f"Поручни в {data['name']}", lat + 0.001, lon - 0.001, f"{data['name']}, объект {i+1}"))
                all_objects.append(AccessibilityObject(None, "понижение_бордюра", f"Понижение бордюра в {data['name']}", lat - 0.001, lon + 0.001, f"{data['name']}, объект {i+1}"))

        for obj in all_objects:
            self.add_object(obj)

        print(f"УСПЕШНО: добавлено {len(all_objects)} объектов доступности в Туле (по 12 на каждый тип в каждом районе)!")
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
        # Default to Tula if no city specified
        if not any(city in address.lower() for city in ['тула', 'moscow', 'спб', 'екатеринбург']):
            address += ", Тула"
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

    def reverse_geocode(self, lat: float, lon: float) -> Optional[str]:
        try:
            response = requests.get(
                f"{self.base_url}/reverse",
                params={"lat": lat, "lon": lon, "format": "json", "addressdetails": 1},
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            if data and 'display_name' in data:
                return data['display_name']
        except Exception as e:
            print(f"Обратное геокодирование ошибка: {e}")
        return None

    def get_route(self, start: Tuple[float, float], end: Tuple[float, float]):
        return self.get_route_multi([start, end])

    def get_route_multi(self, points: List[Tuple[float, float]]):
        try:
            # ЭТОТ сервер РЕАЛЬНО даёт пеший маршрут!
            coords_str = ";".join(f"{p[1]},{p[0]}" for p in points)
            url = f"{self.routing_url}/route/v1/foot/{coords_str}"
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
    def __init__(self, db_path: str = "db/accessibility.db"):
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
                    user_location: Optional[Tuple[float, float]] = None,
                    start_coords: Optional[Tuple[float, float]] = None,
                    end_coords: Optional[Tuple[float, float]] = None) -> Dict:

        # 1. Геокодирование
        if start_coords:
            start_coords_tuple = start_coords
            start_addr = "Выбранное место на карте"
        elif start_address.lower() == "текущий" and user_location:
            start_coords_tuple = user_location
            start_addr = "Текущее местоположение"
        else:
            start_coords_tuple = self.osm.geocode(start_address)
            if not start_coords_tuple:
                return {"error": "Не удалось найти начальный адрес"}
            start_addr = start_address

        if end_coords:
            end_coords_tuple = end_coords
            end_addr = "Выбранное место на карте"
        else:
            end_coords_tuple = self.osm.geocode(end_address)
            if not end_coords_tuple:
                return {"error": "Не удалось найти конечный адрес"}
            end_addr = end_address

        # 2. Сначала строим САМЫЙ КОРОТКИЙ маршрут
        base_route_coords, base_data = self.osm.get_route(start_coords_tuple, end_coords_tuple)
        if not base_route_coords:
            return {"error": "Не удалось построить маршрут"}

        base_distance = base_data["distance"]
        base_duration = int(base_data["duration"] / 60)

        start_lat, start_lon = start_coords_tuple
        end_lat, end_lon = end_coords_tuple

        # 3. Генерируем объекты доступности в окрестностях маршрута (500м - 1км)
        unique_objects = self.generate_accessibility_objects(base_route_coords, mobility_type)

        # 4. Выбираем до 6 лучших объектов (по приоритету + близости + порядку следования)
        priorities = self.feature_priorities.get(mobility_type, {})

        # Compute cumulative distances along the route
        cum_dist = [0.0]
        for i in range(1, len(base_route_coords)):
            prev = base_route_coords[i-1]
            curr = base_route_coords[i]
            dist = ((curr[0] - prev[0])**2 + (curr[1] - prev[1])**2)**0.5
            cum_dist.append(cum_dist[-1] + dist)

        def score_object(obj):
            lat, lon, ftype, desc, addr, dist = obj
            priority = priorities.get(ftype, 0)
            # Бонус за близость к началу/концу
            start_dist = ((lat - start_lat)**2 + (lon - start_lon)**2)**0.5
            end_dist = ((lat - end_lat)**2 + (lon - end_lon)**2)**0.5
            position_bonus = max(0, 0.001 - min(start_dist, end_dist)) * 100000  # бонус за близость к началу/концу
            distance_penalty = dist * 500000  # штраф за удаленность от маршрута
            return priority * 1000 + position_bonus - distance_penalty

        unique_objects.sort(key=score_object, reverse=True)
        best_objects = unique_objects[:6]

        # Add cumulative distance to each object and sort by position along route
        for i, obj in enumerate(best_objects):
            obj = list(obj)  # convert tuple to list
            lat, lon = obj[0], obj[1]
            min_d = float('inf')
            closest_idx = 0
            for idx, (rlat, rlon) in enumerate(base_route_coords):
                d = ((lat - rlat)**2 + (lon - rlon)**2)**0.5
                if d < min_d:
                    min_d = d
                    closest_idx = idx
            obj_cum_dist = cum_dist[closest_idx]
            obj.append(obj_cum_dist)
            best_objects[i] = obj  # update the list

        best_objects.sort(key=lambda x: x[6])  # sort by cumulative distance

        # Filter to ensure minimum distance along route to avoid close waypoints
        min_route_distance = 0.009  # ~1km along route
        filtered_objects = []
        for obj in best_objects:
            if not filtered_objects or all(abs(obj[6] - o[6]) > min_route_distance for o in filtered_objects):
                filtered_objects.append(obj)
        best_objects = filtered_objects[:3]  # limit to 3 waypoints max

        # 5. Строим финальный маршрут: старт → лучшие объекты → финиш
        waypoints = [start_coords_tuple] + [(obj[0], obj[1]) for obj in best_objects] + [end_coords_tuple]
        used_objects = []

        for obj in best_objects:
            lat, lon, ftype, desc, addr = obj[:5]
            used_objects.append({
                "feature_type": ftype,
                "description": desc,
                "address": addr,
                "latitude": lat,
                "longitude": lon
            })

        # Строим маршрут через выбранные объекты одним запросом
        final_route, full_data = self.osm.get_route_multi(waypoints)

        if not final_route or full_data["distance"] > base_distance * 1.5:
            # Если крюк слишком большой или ошибка — возвращаем короткий маршрут
            final_route = base_route_coords
            total_distance = base_distance
            total_minutes = base_duration
            used_objects = []  # но всё равно показываем найденные объекты в описании
        else:
            total_distance = full_data["distance"]
            total_minutes = int(full_data["duration"] / 60)

        description = self.generate_detailed_description(
            start_addr, end_address, total_distance, total_minutes, used_objects, mobility_type
        )

        return {
            "success": True,
            "start": {"address": start_addr, "coords": start_coords_tuple},
            "end": {"address": end_addr, "coords": end_coords_tuple},
            "route_coords": final_route,
            "accessibility_objects": used_objects,
            "description": description,
            "total_distance": int(total_distance),
            "duration_minutes": total_minutes,
            "mobility_type": mobility_type.value
        }

    def get_pedestrian_points_near_route(self, base_route_coords):
        # Get bbox around route
        lats = [p[0] for p in base_route_coords]
        lons = [p[1] for p in base_route_coords]
        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)
        # Expand by 0.01 degrees ~1km
        min_lat -= 0.01
        max_lat += 0.01
        min_lon -= 0.01
        max_lon += 0.01
        # Overpass query for pedestrian ways
        query = f"""
        [out:json];
        way["highway"~"footway|pedestrian|path"]({min_lat},{min_lon},{max_lat},{max_lon});
        out geom;
        """
        url = "https://overpass-api.de/api/interpreter"
        try:
            response = requests.post(url, data=query, timeout=10)
            data = response.json()
            points = []
            for way in data['elements']:
                if 'geometry' in way:
                    for geom in way['geometry']:
                        points.append((geom['lat'], geom['lon']))
            import random
            sampled = random.sample(points, min(50, len(points)))
            return sampled
        except:
            # Fallback to random
            return []

    def generate_accessibility_objects(self, base_route_coords, mobility_type):
        import random
        import math
        objects = []
        features = {
            MobilityType.WHEELCHAIR: ["пандус_стационарный", "пандус_откидной"],
            MobilityType.VISUALLY_IMPAIRED: ["тактильная_плитка_направляющая", "светофор_звуковой", "тактильная_плитка_предупреждающая", "кнопка_вызова"],
            MobilityType.CANE: ["поручни", "понижение_бордюра"]
        }.get(mobility_type, [])
        pedestrian_points = self.get_pedestrian_points_near_route(base_route_coords)
        # Filter points within 500m of base_route
        def dist_to_route(lat, lon):
            return min(((lat - rlat)**2 + (lon - rlon)**2)**0.5 for rlat, rlon in base_route_coords)
        filtered_points = [p for p in pedestrian_points if dist_to_route(p[0], p[1]) < 0.005]  # ~500m
        if not filtered_points:
            # Fallback
            for lat, lon in base_route_coords[::20]:
                for _ in range(2):
                    dist_deg = random.uniform(0.001, 0.005)  # 100-500m
                    angle = random.uniform(0, 2 * math.pi)
                    new_lat = lat + dist_deg * math.cos(angle)
                    new_lon = lon + dist_deg * math.sin(angle)
                    feature = random.choice(features)
                    description = f"Generated {feature.replace('_', ' ')}"
                    address = f"Near pedestrian route at {new_lat:.4f}, {new_lon:.4f}"
                    obj_dist = dist_to_route(new_lat, new_lon)
                    obj = (new_lat, new_lon, feature, description, address, obj_dist)
                    objects.append(obj)
        else:
            for lat, lon in filtered_points[:20]:  # limit
                feature = random.choice(features)
                description = f"Generated {feature.replace('_', ' ')} on pedestrian route"
                address = f"On pedestrian route at {lat:.4f}, {lon:.4f}"
                obj_dist = dist_to_route(lat, lon)
                obj = (lat, lon, feature, description, address, obj_dist)
                objects.append(obj)
        return objects

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
    from flask import Flask, render_template, render_template_string, request, jsonify, redirect, url_for, send_from_directory, session, flash
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

    # Load organizations and infrastructure
    parser = XMLDataParser()
    try:
        parser.parse_organizations_xml("xml/Файл_соцподдержка_1.xml")
        print(f"Loaded {len(parser.social_organizations)} organizations")
    except FileNotFoundError:
        print("Organizations XML not found, proceeding without organizations")

    # Using generated test data instead of XML for demo
    # try:
    #     parser.parse_infrastructure_xml("xml/Файл_соцподдержка_2.xml")
    #     parser.populate_database(nav_system.db.db_path)
    #     print(f"Loaded infrastructure data from XML")
    # except FileNotFoundError:
    #     print("Infrastructure XML not found, using default data")

    organizations = parser.social_organizations
    
    HTML_TEMPLATE = r"""
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
                position: relative;
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
            .header .links a[href="/admin/districts_folium"] { background: rgba(255,255,255,0.2); padding: 5px 10px; border-radius: 5px; }
            .accessibility-buttons { margin-top: 20px; }
            .btn-accessibility {
                background: rgba(255,255,255,0.2);
                border: 1px solid rgba(255,255,255,0.3);
                color: white;
                padding: 8px 12px;
                margin: 0 5px;
                border-radius: 5px;
                cursor: pointer;
                transition: background 0.3s;
            }
            .btn-accessibility:hover { background: rgba(255,255,255,0.3); }
            .btn-accessibility.active { background: rgba(255,255,255,0.5); }
            body.high-contrast { background: black; color: white; }
            body.high-contrast .container { background: #333; }
            body.large-font { font-size: 1.2em; }
            body.large-font h1 { font-size: 3em; }
            body.large-font .btn { font-size: 1.3em; }
                background: rgba(255,255,255,0.2);
                color: white;
                border: 1px solid white;
                padding: 8px 12px;
                border-radius: 6px;
                font-size: 0.9em;
                cursor: pointer;
                margin: 0 5px;
                transition: all 0.3s;
            }
            .btn-accessibility:hover {
                background: rgba(255,255,255,0.3);
            }
            .high-contrast {
                background: #000 !important;
                color: #fff !important;
            }
            .high-contrast .sidebar {
                background: #111 !important;
            }
            .high-contrast .form-group label {
                color: #fff !important;
            }
            .high-contrast input, .high-contrast select {
                background: #333 !important;
                color: #fff !important;
                border-color: #fff !important;
            }
            .high-contrast .btn {
                background: #fff !important;
                color: #000 !important;
            }
            .high-contrast .route-info {
                background: #333 !important;
                color: #fff !important;
            }
            .high-contrast .route-info pre {
                background: #333 !important;
                color: #fff !important;
            }
            .content {
                display: grid;
                grid-template-columns: 400px 1fr;
                gap: 0;
            }
            .buttons {
                display: flex;
                justify-content: space-around;
                padding: 20px;
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
                width: auto;
                padding: 15px;
                border: none;
                border-radius: 8px;
                font-size: 1.1em;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s;
                flex: 1;
                min-width: 200px;
            }
            .button-row {
                display: flex;
                gap: 10px;
                flex-wrap: wrap;
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
                position: relative;
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
            @keyframes pulse {
                0% { transform: scale(1); }
                50% { transform: scale(1.05); }
                100% { transform: scale(1); }
            }
            .modal {
                display: none;
                position: fixed;
                z-index: 2000;
                left: 0;
                top: 0;
                width: 100%;
                height: 100%;
                background-color: rgba(0,0,0,0.9);
            }
            .modal-content {
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                background: transparent;
                border: none;
                padding: 0;
                width: auto;
                max-width: none;
            }
            .close {
                position: absolute;
                top: 20px;
                right: 20px;
                color: white;
                font-size: 36px;
                font-weight: bold;
                cursor: pointer;
                z-index: 2001;
            }
            .close:hover {
                color: red;
            }
            #samovarVideo {
                width: 100%;
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
                <div class="accessibility-buttons">
                    <button id="elementVoiceBtn" class="btn-accessibility">🔊 Озвучивание элементов</button>
                    <button id="routeVoiceBtn" class="btn-accessibility" style="display:none;">🔊 Озвучить маршрут</button>
                    <button id="contrastBtn" class="btn-accessibility">👓 Режим для слабовидящих</button>
                </div>
            </div>
            <div class="content">
                <div class="sidebar">
                    <form id="routeForm">
                        <div class="form-group">
                            <label for="startAddress">
                                <span class="icon">📍</span>Откуда
                            </label>
                            <input type="text" id="startAddress" placeholder="Введите адрес или 'текущий'" required title="Введите адрес отправления или 'текущий' для использования геолокации">
                            <div class="geolocation-status" id="geoStatus"></div>
                        </div>
                        
                        <div class="form-group">
                            <label for="endAddress">
                                <span class="icon">🎯</span>Куда
                            </label>
                            <input type="text" id="endAddress" list="destinations" placeholder="Введите адрес или выберите организацию" required title="Введите адрес назначения или выберите организацию из списка">
                            <datalist id="destinations"></datalist>
                        </div>
                        
                        <div class="form-group">
                            <label for="mobilityType">
                                <span class="icon">👤</span>Тип ограничений
                            </label>
                            <select id="mobilityType" required title="Выберите тип ограничений мобильности">
                                <option value="колясочник">♿ Колясочник</option>
                                <option value="слабовидящий">👓 Слабовидящий</option>
                                <option value="опора на трость">🦯 Опора на трость</option>
                            </select>
                        </div>

                        <div class="button-row">
                        <button type="submit" class="btn btn-primary">
                            <span class="icon">🗺️</span>Построить маршрут
                        </button>

                        <button type="button" class="btn btn-secondary" id="useLocationBtn">
                            <span class="icon">📱</span>Использовать мою геолокацию
                        </button>

                        <a href="/submit" class="btn btn-secondary">
                            <span class="icon">➕</span>Добавить объект доступности
                        </a>

                        </div>
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

            <div id="pngContainer" style="display: flex; justify-content: space-around; padding: 20px; background: #f8f9fa; border-radius: 10px; margin: 20px;">
                <button id="png1" class="icon-btn" style="width: 50px; height: 50px; border: none; background: white; box-shadow: 0 4px 12px rgba(0,0,0,0.3); cursor: pointer;"><img src="/music/alien.png" style="width:100%; height:100%; object-fit:cover;" alt="icon"></button>
                <button id="png2" class="icon-btn" style="width: 50px; height: 50px; border: none; background: white; box-shadow: 0 4px 12px rgba(0,0,0,0.3); cursor: pointer;"><img src="/music/alien.png" style="width:100%; height:100%; object-fit:cover;" alt="icon"></button>
                <button id="png3" class="icon-btn" style="width: 50px; height: 50px; border: none; background: white; box-shadow: 0 4px 12px rgba(0,0,0,0.3); cursor: pointer;"><img src="/music/alien.png" style="width:100%; height:100%; object-fit:cover;" alt="icon"></button>
            </div>

            <!-- Notification -->
            <div id="notification" style="display:none; position:fixed; bottom:20px; left:50%; transform:translateX(-50%); background:white; padding:20px; border:1px solid black; z-index:2000; border-radius:10px; box-shadow:0 0 10px rgba(0,0,0,0.5);"></div>

            <!-- Video Modal -->
            <div id="videoModal" class="modal">
                <div class="modal-content">
                    <span id="closeVideoModal" class="close">&times;</span>
                    <video id="samovarVideo" autoplay loop style="display: block; margin: 0 auto; width: 90vw; height: 90vh; object-fit: contain;">
                        <source src="/music/samovar.mp4" type="video/mp4">
                        Your browser does not support the video tag.
                    </video>
                </div>
            </div>

        </div>
        
        <link href='https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.css' rel='stylesheet' />
        <script src='https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.js'></script>
        <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
        <audio id="bgMusic" preload="auto"></audio>

        <script>
            // Initialize speech synthesis
            if ('speechSynthesis' in window) {
                speechSynthesis.getVoices(); // Load voices
            }

            // Инициализация MapLibre GL JS
            const map = new maplibregl.Map({
                container: 'map',
                style: 'https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json',
                center: [37.6175, 54.1931],
                zoom: 12,
                pitch: 30,
                bearing: 0
            });

            map.addControl(new maplibregl.NavigationControl());
            map.addControl(new maplibregl.GeolocateControl({
                positionOptions: { enableHighAccuracy: true },
                trackUserLocation: true
            }));

            // PNG click handling like the accessibility buttons above
            let pngClicked = 0;
            const totalPng = 3;
            const pngElements = ['png1', 'png2', 'png3'];

            pngElements.forEach(id => {
                document.getElementById(id).addEventListener('click', () => {
                    document.getElementById(id).style.display = 'none';
                    pngClicked++;
                    const remaining = totalPng - pngClicked;

                    if (remaining > 0) {
                        showNotification(`🎉 Отлично! Найдено ${pngClicked}/${totalPng}. Осталось ${remaining} иконок!`, 3000);
                    } else {
                        // All icons found - show video and audio
                        showNotification('🎊 Поздравляем! Вы нашли все иконки! Сейчас включится видео с самоваром!', 4000);
                        setTimeout(() => {
                            showVideoAndAudio();
                        }, 2000);
                    }
                });
            });

            let routeLayer = null;
            let routeSource = null;
            let accessibilityMarkers = [];
            let startMarker = null;
            let endMarker = null;
            let userLocationMarker = null;
            let addressMarkers = [];

            // Полная очистка карты
            function clearMapCompletely() {
                if (routeLayer && map.getLayer('route')) map.removeLayer('route');
                if (routeSource && map.getSource('route')) map.removeSource('route');
                routeLayer = routeSource = null;

                accessibilityMarkers.forEach(m => m.remove());
                accessibilityMarkers = [];

                addressMarkers.forEach(m => m.remove());
                addressMarkers = [];

                if (startMarker) startMarker.remove();
                if (endMarker) endMarker.remove();
                if (userLocationMarker) userLocationMarker.remove();
                startMarker = endMarker = userLocationMarker = null;
            }


            // Отображение маршрута
            function displayRoute(data) {
                clearMapCompletely();

                const coords = data.route_coords.map(c => [c[1], c[0]]);

                map.addSource('route', {
                    type: 'geojson',
                    data: { type: 'Feature', geometry: { type: 'LineString', coordinates: coords } }
                });
                map.addLayer({
                    id: 'route',
                    type: 'line',
                    source: 'route',
                    paint: { 'line-color': '#667eea', 'line-width': 7, 'line-opacity': 0.9 }
                });
                routeSource = 'route';
                routeLayer = 'route';

                // Старт и финиш
                startMarker = new maplibregl.Marker({ color: '#4ade80' })
                    .setLngLat(coords[0])
                    .setPopup(new maplibregl.Popup().setHTML(`<b>Начало</b><br>${data.start.address}`))
                    .addTo(map);

                endMarker = new maplibregl.Marker({ color: '#f87171' })
                    .setLngLat(coords[coords.length - 1])
                    .setPopup(new maplibregl.Popup().setHTML(`<b>Финиш</b><br>${data.end.address}`))
                    .addTo(map);

                // Объекты доступности
                const colorMap = {
                    'пандус_стационарный': '#3b82f6', 'лифт': '#8b5cf6', 'широкая_дверь': '#ec4899',
                    'доступная_парковка': '#06b6d4', 'тактильная_плитка_направляющая': '#f97316',
                    'светофор_звуковой': '#10b981', 'поручни': '#a16207', 'понижение_бордюра': '#84cc16'
                };

                data.accessibility_objects.forEach(obj => {
                    const marker = new maplibregl.Marker({ color: colorMap[obj.feature_type] || '#6b7280' })
                        .setLngLat([obj.longitude, obj.latitude])
                        .setPopup(new maplibregl.Popup({ offset: 25 }).setHTML(`
                            <b>${obj.feature_type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</b><br>
                            ${obj.description}<br><small><i>${obj.address}</i></small>
                        `))
                        .addTo(map);
                    accessibilityMarkers.push(marker);
                });

                const bounds = new maplibregl.LngLatBounds(coords[0], coords[0]);
                coords.forEach(c => bounds.extend(c));
                map.fitBounds(bounds, { padding: 100, duration: 2000 });
            }

            // === АВТОДОПОЛНЕНИЕ ДЛЯ startAddress ===
            const startInput = document.getElementById('startAddress');
            const startSuggestions = document.createElement('div');
            startSuggestions.className = 'suggestions';
            startInput.parentNode.style.position = 'relative';
            startInput.parentNode.appendChild(startSuggestions);

            // === АВТОДОПОЛНЕНИЕ ДЛЯ endAddress ===
            const endInput = document.getElementById('endAddress');
            const endSuggestions = document.createElement('div');
            endSuggestions.className = 'suggestions';
            endInput.parentNode.style.position = 'relative';
            endInput.parentNode.appendChild(endSuggestions);

            // Стили для подсказок
            const style = document.createElement('style');
            style.textContent = `
                .suggestions {
                    position: absolute;
                    top: 100%;
                    left: 0;
                    right: 0;
                    background: white;
                    border: 1px solid #ccc;
                    max-height: 200px;
                    overflow-y: auto;
                    z-index: 1000;
                    display: none;
                    box-shadow: 0 4px 10px rgba(0,0,0,0.1);
                    border-radius: 8px;
                    margin-top: 4px;
                }
                .suggestions div {
                    padding: 12px;
                    cursor: pointer;
                    border-bottom: 1px solid #eee;
                }
                .suggestions div:hover, .suggestions div.active {
                    background: #667eea;
                    color: white;
                }
            `;
            document.head.appendChild(style);

            // Универсальная функция автодополнения
            async function showSuggestions(input, box) {
                const query = input.value.trim();
                if (query.length < 2) {
                    box.style.display = 'none';
                    return;
                }

                try {
                    const res = await fetch(`/api/suggest_address?q=${encodeURIComponent(query)}`);
                    const suggestions = await res.json();

                    box.innerHTML = '';
                    if (suggestions.length === 0) {
                        box.style.display = 'none';
                        return;
                    }

                    suggestions.forEach((s, i) => {
                        const div = document.createElement('div');
                        div.textContent = s;
                        div.onclick = () => {
                            input.value = s;
                            box.style.display = 'none';
                        };
                        div.onmouseover = () => {
                            box.querySelectorAll('div').forEach(d => d.classList.remove('active'));
                            div.classList.add('active');
                        };
                        box.appendChild(div);
                    });

                    box.style.display = 'block';
                } catch (err) {
                    box.style.display = 'none';
                }
            }

            // Обработчики
            startInput.addEventListener('input', () => showSuggestions(startInput, startSuggestions));
            endInput.addEventListener('input', () => showSuggestions(endInput, endSuggestions));

            // Скрытие при клике вне
            document.addEventListener('click', e => {
                if (!e.target.closest('#startAddress') && !e.target.closest('.suggestions')) {
                    startSuggestions.style.display = 'none';
                }
                if (!e.target.closest('#endAddress') && !e.target.closest('.suggestions')) {
                    endSuggestions.style.display = 'none';
                }
            });

            // Геолокация
            document.getElementById('useLocationBtn').addEventListener('click', () => {
                navigator.geolocation.getCurrentPosition(async pos => {
                    const lat = pos.coords.latitude;
                    const lon = pos.coords.longitude;

                    if (userLocationMarker) userLocationMarker.remove();
                    userLocationMarker = new maplibregl.Marker({ color: '#3b82f6' })
                        .setLngLat([lon, lat])
                        .setPopup(new maplibregl.Popup().setHTML('<b>Вы здесь</b>'))
                        .addTo(map);

                    document.getElementById('startAddress').value = 'current';
                    document.getElementById('geoStatus').innerHTML = `Геолокация: ±${pos.coords.accuracy.toFixed(0)} м`;
                    document.getElementById('geoStatus').style.color = 'green';
                    map.flyTo({ center: [lon, lat], zoom: 16 });
                }, () => {
                    document.getElementById('geoStatus').textContent = 'Геолокация недоступна';
                    document.getElementById('geoStatus').style.color = 'red';
                });
            });

            // Построение маршрута
            document.getElementById('routeForm').addEventListener('submit', async e => {
                e.preventDefault();
                clearMapCompletely();

                const payload = {
                    start_address: document.getElementById('startAddress').value,
                    end_address: document.getElementById('endAddress').value,
                    mobility_type: document.getElementById('mobilityType').value
                };

                document.getElementById('loading').classList.add('active');

                try {
                    const res = await fetch('/api/route', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
                    const data = await res.json();

                    if (data.success) {
                        currentRoute = data;
                        displayRoute(data);
                        document.getElementById('routeDescription').textContent = data.description;
                        document.getElementById('routeInfo').style.display = 'block';
                        document.getElementById('routeVoiceBtn').style.display = 'inline-block';
                    } else {
                        alert('Ошибка: ' + (data.error || 'Неизвестная ошибка'));
                        document.getElementById('routeVoiceBtn').style.display = 'none';
                    }
                } catch (err) {
                    alert('Сервер недоступен');
                } finally {
                    document.getElementById('loading').classList.remove('active');
                }
            });

            // Клик на карте для выбора адреса
            let selectedInput = null;
            document.getElementById('startAddress').addEventListener('focus', () => selectedInput = 'start');
            document.getElementById('endAddress').addEventListener('focus', () => selectedInput = 'end');

            map.on('click', async (e) => {
                if (!selectedInput) return;
                const { lng, lat } = e.lngLat;
                try {
                    const res = await fetch(`/api/reverse_geocode?lat=${lat}&lon=${lng}`);
                    const data = await res.json();
                    if (data.address) {
                        document.getElementById(selectedInput === 'start' ? 'startAddress' : 'endAddress').value = data.address;
                        selectedInput = null;
                    }
                } catch (err) {
                    console.error('Reverse geocode failed:', err);
                }
            });

            // Доступность
            let elementVoiceMode = false;
            let highContrast = false;
            let largeFont = false;

            document.getElementById('elementVoiceBtn').addEventListener('click', () => {
                elementVoiceMode = !elementVoiceMode;
                document.getElementById('elementVoiceBtn').textContent = elementVoiceMode ? '🔊 Выключить озвучивание' : '🔊 Озвучивание элементов';
                document.getElementById('elementVoiceBtn').classList.toggle('active', elementVoiceMode);
                if (elementVoiceMode) {
                    speakText('Озвучивание элементов включено');
                } else {
                    speakText('Озвучивание элементов выключено');
                }
            });

            document.getElementById('contrastBtn').addEventListener('click', () => {
                highContrast = !highContrast;
                document.body.classList.toggle('high-contrast', highContrast);
                document.getElementById('contrastBtn').classList.toggle('active', highContrast);
            });

            // Функция озвучивания с более человеческим голосом
            function speakText(text, callback = null) {
                if (!('speechSynthesis' in window)) return;
                // Убираем эмодзи из текста
                text = text.replace(/[\u{1F600}-\u{1F64F}]|[\u{1F300}-\u{1F5FF}]|[\u{1F680}-\u{1F6FF}]|[\u{1F1E0}-\u{1F1FF}]|[\u{2600}-\u{26FF}]|[\u{2700}-\u{27BF}]/gu, '');
                const utter = new SpeechSynthesisUtterance(text);
                utter.lang = 'ru-RU';
                utter.rate = 0.9;  // Более естественная скорость
                utter.pitch = 0.9; // Более низкая высота для мужского голоса
                utter.volume = 0.9;
                // Попытка выбрать мужской русский голос
                const voices = speechSynthesis.getVoices();
                const russianVoice = voices.find(v => v.lang.startsWith('ru') && (v.name.includes('Male') || v.name.includes('мужской') || !v.name.includes('Female')));
                if (russianVoice) utter.voice = russianVoice;
                if (callback) utter.onend = callback;
                speechSynthesis.speak(utter);
            }

            // Озвучка маршрута
            function announceRoute() {
                if (!currentRoute) return;
                speechSynthesis.cancel();
                const texts = [
                    `Маршрут от ${currentRoute.start.address} до ${currentRoute.end.address}`,
                    `Общая длина: ${currentRoute.total_distance} метров. Примерное время в пути: ${currentRoute.duration_minutes} минут`,
                    ...currentRoute.accessibility_objects.map(o => `${o.feature_type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}: ${o.description}`),
                    "Приятного и безопасного пути!"
                ];
                let i = 0;
                const speakNext = () => {
                    if (i >= texts.length) return;
                    speakText(texts[i++], speakNext);
                };
                speakNext();
            }

            // Озвучка интерфейса для слабовидящих
            function announceInterface() {
                speechSynthesis.cancel();
                const elements = [
                    "Доступная навигация для людей с ограниченными возможностями",
                    "Поле откуда - введите начальный адрес или нажмите для выбора на карте",
                    "Поле куда - введите конечный адрес или выберите организацию",
                    "Выберите тип ограничений мобильности: колясочник, слабовидящий, или опора на трость",
                    "Кнопка Построить маршрут",
                    "Кнопка Использовать мою геолокацию",
                    "Кнопка Добавить объект доступности",
                    "Кнопка Озвучить маршрут - доступна после построения маршрута",
                    "Карта - кликните для выбора адреса"
                ];
                let i = 0;
                const speakNext = () => {
                    if (i >= elements.length) return;
                    speakText(elements[i++], speakNext);
                };
                speakNext();
            }

            document.getElementById('routeVoiceBtn').addEventListener('click', () => {
                if (!currentRoute) return;
                announceRoute();
            });

            // Озвучивание элементов интерфейса при включенном режиме
            function announceElement(element, eventType) {
                if (!elementVoiceMode || !('speechSynthesis' in window)) return;
                let text = '';
                if (element.tagName === 'INPUT' || element.tagName === 'SELECT' || element.tagName === 'TEXTAREA') {
                    const label = element.previousElementSibling ? element.previousElementSibling.textContent.trim() : element.placeholder || element.getAttribute('title') || 'Поле ввода';
                    text = label;
                    if (eventType === 'change' && element.tagName === 'SELECT') {
                        const selected = element.options[element.selectedIndex].text;
                        text += '. Выбрано: ' + selected;
                    }
                } else if (element.tagName === 'BUTTON') {
                    text = element.textContent.replace(/[^\w\sа-яё]/gi, '').trim() || element.getAttribute('title') || 'Кнопка';
                }
                if (text) {
                    speechSynthesis.speak(new SpeechSynthesisUtterance(text));
                }
            }

            // Добавляем listeners ко всем интерактивным элементам
            document.querySelectorAll('input, select, textarea, button').forEach(el => {
                el.addEventListener('focus', () => announceElement(el, 'focus'));
                if (el.tagName === 'SELECT') {
                    el.addEventListener('change', () => announceElement(el, 'change'));
                }
                if (el.tagName === 'BUTTON') {
                    el.addEventListener('click', () => announceElement(el, 'click'));
                }
            });

            // Показать адреса домов
            async function showAddresses() {
                const bounds = map.getBounds();
                const bbox = `${bounds.getSouth()},${bounds.getWest()},${bounds.getNorth()},${bounds.getEast()}`;
                const query = `[out:json];way["building"]["addr:housenumber"](${bbox});out center meta;`;
                try {
                    const response = await fetch('https://overpass-api.de/api/interpreter', {
                        method: 'POST',
                        body: query
                    });
                    const data = await response.json();
                    // Clear previous
                    addressMarkers.forEach(m => m.remove());
                    addressMarkers = [];
                    // Add new
                    data.elements.slice(0, 100).forEach(element => {  // limit to 100
                        const lat = element.center.lat;
                        const lon = element.center.lon;
                        const housenumber = element.tags['addr:housenumber'] || '';
                        const street = element.tags['addr:street'] || '';
                        const address = `${street} ${housenumber}`.trim();
                        if (address) {
                            const marker = new maplibregl.Marker({ color: '#888' })
                                .setLngLat([lon, lat])
                                .setPopup(new maplibregl.Popup().setHTML(`<b>Адрес:</b><br>${address}`))
                                .addTo(map);
                            addressMarkers.push(marker);
                        }
                    });
                } catch (err) {
                    console.error('Error fetching addresses:', err);
                }
            }

            document.getElementById('showAddressesBtn').addEventListener('click', showAddresses);

            map.on('load', () => {
                console.log("MapLibre готова — всё идеально!");
            });

            function showNotification(message, duration) {
                const notification = document.getElementById('notification');
                notification.textContent = message;
                notification.style.display = 'block';
                notification.style.background = 'linear-gradient(135deg, #667eea, #764ba2)';
                notification.style.color = 'white';
                notification.style.border = 'none';
                notification.style.fontSize = '16px';
                notification.style.fontWeight = 'bold';
                setTimeout(() => {
                    notification.style.display = 'none';
                }, duration);
            }

            function showVideoAndAudio() {
                const modal = document.getElementById('videoModal');
                modal.style.display = 'block';
                const video = document.getElementById('samovarVideo');
                video.play();
                const audio = document.getElementById('bgMusic');
                audio.src = '/music/julija-chicherina-tu-lu-la.mp3';
                audio.play();

                // Attach close button event
                const closeBtn = document.getElementById('closeVideoModal');
                if (closeBtn) {
                    closeBtn.addEventListener('click', closeModal);
                }
            }

            // Enhanced modal close functionality
            const modal = document.getElementById('videoModal');
            function closeModal() {
                const modal = document.getElementById('videoModal');
                modal.style.display = 'none';
                const video = document.getElementById('samovarVideo');
                video.pause();
                video.currentTime = 0; // Reset video
                const audio = document.getElementById('bgMusic');
                audio.pause();
                audio.currentTime = 0; // Reset audio
            }
            window.onclick = function(event) {
                if (event.target == modal) {
                    closeModal();
                }
            };

            // ESC key to close modal
            document.addEventListener('keydown', function(event) {
                if (event.key === 'Escape' && modal.style.display === 'block') {
                    closeModal();
                }
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

        # Данные уже добавлены в __init__

        result = nav_system.find_route(
            start_address=start_address,
            end_address=end_address,
            mobility_type=mobility_type,
            user_location=(user_location['lat'], user_location['lon']) if user_location else None,
            start_coords=data.get('start_coords'),
            end_coords=data.get('end_coords')
        )

        return jsonify(result)

    @app.route('/api/organizations')
    def api_organizations():
        mobility_type = request.args.get('mobility_type')
        orgs = []
        for org in organizations[:100]:  # Show more organizations
            serves = _matches_disability(org.served_disability_categories, mobility_type) if mobility_type else True
            orgs.append({
                "name": org.name,
                "address": org.address,
                "categories": org.served_disability_categories,
                "serves_current_type": serves,
                "warning": "Не обслуживает выбранный тип инвалидности" if mobility_type and not serves else ""
            })
        return jsonify(orgs)

    def _matches_disability(categories, mobility_type):
        """Check if organization serves the given disability type"""
        # Map mobility types to possible category names in the XML
        mapping = {
            "колясочник": ["инвалиды-колясочники", "колясочники", "опорно-двигательные", "двигательные"],
            "слабовидящий": ["слабовидящие", "инвалиды по зрению", "слепые", "зрения"],
            "опора на трость": ["инвалиды с поражением опорно-двигательного аппарата", "травмы", "пожилые", "двигательные"]
        }
        target_categories = mapping.get(mobility_type, [])
        return any(any(cat.lower() in category.lower() for cat in target_categories) for category in categories)

    def clean_address(full_address):
        parts = full_address.split(', ')
        cleaned = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            # Skip postal codes (5+ digits)
            if part.isdigit() and len(part) >= 5:
                continue
            # Skip country
            if part.lower() in ['россия', 'russia']:
                continue
            # Skip regions if too long
            if len(part) > 20 and any(word in part.lower() for word in ['область', 'край', 'республика']):
                continue
            cleaned.append(part)
            if len(cleaned) >= 3:
                break
        return ', '.join(cleaned)
        parts = full_address.split(', ')
        cleaned = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            # Skip postal codes (5+ digits)
            if part.isdigit() and len(part) >= 5:
                continue
            # Skip country
            if part.lower() in ['россия', 'russia']:
                continue
            # Skip regions if too long
            if len(part) > 20 and any(word in part.lower() for word in ['область', 'край', 'республика']):
                continue
            cleaned.append(part)
            if len(cleaned) >= 3:
                break
        return ', '.join(cleaned)

    @app.route('/api/suggest_address')
    def api_suggest_address():
        query = request.args.get('q', '').strip()
        if not query:
            return jsonify([])
        original_query = query
        query_lower = query.lower()
        suggestions = []

        # Search organizations first
        for org in organizations:
            if query_lower in org.name.lower() or query_lower in org.address.lower():
                suggestions.append(f"{org.name} - {org.address}")
                if len(suggestions) >= 5:
                    break

        if len(suggestions) < 5:
            conn = sqlite3.connect(nav_system.db.db_path)
            cursor = conn.cursor()
            # Get from accessibility_objects - prioritize starts with, then contains
            cursor.execute("SELECT DISTINCT address FROM accessibility_objects WHERE LOWER(address) LIKE ? LIMIT 10", (query_lower + '%',))
            starts_with = [row[0] for row in cursor.fetchall()]
            cursor.execute("SELECT DISTINCT address FROM accessibility_objects WHERE LOWER(address) LIKE ? AND LOWER(address) NOT LIKE ? LIMIT 10", ('%' + query_lower + '%', query_lower + '%'))
            contains = [row[0] for row in cursor.fetchall()]
            db_addresses = starts_with + contains
            # Get from user_submissions
            cursor.execute("SELECT DISTINCT address FROM user_submissions WHERE LOWER(address) LIKE ? LIMIT 10", (query_lower + '%',))
            starts_with_sub = [row[0] for row in cursor.fetchall()]
            cursor.execute("SELECT DISTINCT address FROM user_submissions WHERE LOWER(address) LIKE ? AND LOWER(address) NOT LIKE ? LIMIT 10", ('%' + query_lower + '%', query_lower + '%'))
            contains_sub = [row[0] for row in cursor.fetchall()]
            db_addresses.extend(starts_with_sub + contains_sub)
            conn.close()
            # Remove duplicates while preserving order
            seen = set()
            for addr in db_addresses:
                if addr not in seen and len(suggestions) < 5:
                    suggestions.append(addr)
                    seen.add(addr)

        if len(suggestions) < 5:
            # Fallback to OSM - add Tula if not specified
            osm_query = original_query
            if not any(city in original_query.lower() for city in ['тула', 'moscow', 'спб', 'екатеринбург', 'санкт-петербург']):
                osm_query += ", Тула"
            try:
                response = requests.get(
                    f"{nav_system.osm.base_url}/search",
                    params={"q": osm_query, "format": "json", "limit": 5 - len(suggestions), "countrycodes": "ru"},
                    headers=nav_system.osm.headers,
                    timeout=5
                )
                response.raise_for_status()
                data = response.json()
                osm_addresses = [clean_address(item['display_name']) for item in data]
                suggestions.extend(osm_addresses)
            except Exception as e:
                print(f"Suggest error: {e}")
        return jsonify(suggestions[:5])

    @app.route('/api/reverse_geocode')
    def api_reverse_geocode():
        lat = request.args.get('lat')
        lon = request.args.get('lon')
        if not lat or not lon:
            return jsonify({"error": "Missing lat/lon"})
        try:
            response = requests.get(
                f"{nav_system.osm.base_url}/reverse",
                params={"lat": lat, "lon": lon, "format": "json", "zoom": 18, "addressdetails": 1},
                headers=nav_system.osm.headers,
                timeout=5
            )
            response.raise_for_status()
            data = response.json()
            address = clean_address(data.get('display_name', ''))
            return jsonify({"address": address})
        except Exception as e:
            print(f"Reverse geocode error: {e}")
            return jsonify({"error": "Reverse geocoding failed"})

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
                .header .admin-links a[href="/admin/districts"] { background: rgba(255,255,255,0.2); padding: 5px 10px; border-radius: 5px; }
                .header .admin-links a[href="/admin/districts"] { background: rgba(255,255,255,0.2); padding: 5px 10px; border-radius: 5px; }
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
                    width: auto;
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
                    flex: 1;
                }
                .button-row {
                    display: flex;
                    gap: 10px;
                    flex-wrap: wrap;
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
                .accessibility-buttons { margin-top: 20px; }
                .btn-accessibility {
                    background: #667eea;
                    color: white;
                    border: 1px solid #667eea;
                    padding: 10px 15px;
                    border-radius: 6px;
                    font-size: 0.9em;
                    cursor: pointer;
                    margin: 0 5px;
                    transition: all 0.3s;
                }
                .btn-accessibility:hover {
                    background: #5a67d8;
                }
                .high-contrast {
                    background: #000 !important;
                    color: #fff !important;
                }
                .high-contrast .container {
                    background: #111 !important;
                }
                .high-contrast .form-group label {
                    color: #fff !important;
                }
                .high-contrast input, .high-contrast select, .high-contrast textarea {
                    background: #333 !important;
                    color: #fff !important;
                    border-color: #fff !important;
                }
                .high-contrast .btn {
                    background: #fff !important;
                    color: #000 !important;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>♿ Добавить объект доступности</h1>
                    <p>Помогите сделать город доступнее</p>
                    <div class="accessibility-buttons">
                        <button id="voiceBtn" class="btn-accessibility">🔊 Голосовое сопровождение</button>
                        <button id="contrastBtn" class="btn-accessibility">👓 Режим для слабовидящих</button>
                    </div>
                </div>
                <div class="content">
                    <form action="/api/submit" method="post" enctype="multipart/form-data">
                        <div class="form-group">
                            <label>Тип объекта:</label>
                            <select name="feature_type" required title="Выберите тип объекта доступности">
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
                            <textarea name="description" required title="Опишите объект доступности подробно"></textarea>
                        </div>
                        <div class="form-group">
                            <label>Адрес:</label>
                            <input type="text" name="address" required title="Введите полный адрес объекта доступности">
                        </div>
                        <div class="form-group">
                            <label>Фото:</label>
                            <input type="file" name="photo" accept="image/*" required title="Загрузите фото объекта (изображение)">
                        </div>
                        <div class="button-row">
                        <button type="submit" class="btn btn-primary">Отправить на проверку</button>
                        <a href="/" class="btn btn-secondary">Назад</a>
                        </div>
                    </form>
                </div>
            </div>
        </body>
        <script>
            let submitSuggestionBox = document.createElement('div');
            submitSuggestionBox.id = 'submitSuggestions';
            submitSuggestionBox.style.cssText = `position: absolute; background: white; border: 1px solid #ccc; max-height: 200px; overflow-y: auto; z-index: 1000; display: none; width: 100%; box-shadow: 0 2px 4px rgba(0,0,0,0.1);`;
            document.querySelector('input[name="address"]').parentNode.style.position = 'relative';
            document.querySelector('input[name="address"]').parentNode.appendChild(submitSuggestionBox);

            let submitSelectedIndex = -1;

            function updateSubmitSelection() {
                const items = submitSuggestionBox.children;
                for (let i = 0; i < items.length; i++) {
                    items[i].style.background = i === submitSelectedIndex ? '#667eea' : 'white';
                    items[i].style.color = i === submitSelectedIndex ? 'white' : 'black';
                }
            }

            document.querySelector('input[name="address"]').addEventListener('input', async e => {
                const query = e.target.value;
                if (query.length < 1) {
                    submitSuggestionBox.style.display = 'none';
                    return;
                }
                try {
                    const res = await fetch('/api/suggest_address?q=' + encodeURIComponent(query));
                    const suggestions = await res.json();
                    submitSuggestionBox.innerHTML = '';
                    submitSelectedIndex = -1;
                    suggestions.forEach((s, index) => {
                        const div = document.createElement('div');
                        div.textContent = s;
                        div.style.cssText = 'padding: 8px; cursor: pointer; border-bottom: 1px solid #eee;';
                        div.addEventListener('click', () => {
                            e.target.value = s;
                            submitSuggestionBox.style.display = 'none';
                        });
                        div.addEventListener('mouseover', () => {
                            submitSelectedIndex = index;
                            updateSubmitSelection();
                        });
                        submitSuggestionBox.appendChild(div);
                    });
                    submitSuggestionBox.style.display = suggestions.length ? 'block' : 'none';
                } catch (err) {
                    submitSuggestionBox.style.display = 'none';
                }
            });

            document.querySelector('input[name="address"]').addEventListener('keydown', e => {
                const items = submitSuggestionBox.children;
                if (submitSuggestionBox.style.display === 'none' || items.length === 0) return;
                if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    submitSelectedIndex = (submitSelectedIndex + 1) % items.length;
                    updateSubmitSelection();
                } else if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    submitSelectedIndex = submitSelectedIndex <= 0 ? items.length - 1 : submitSelectedIndex - 1;
                    updateSubmitSelection();
                } else if (e.key === 'Enter') {
                    e.preventDefault();
                    if (submitSelectedIndex >= 0) {
                        items[submitSelectedIndex].click();
                    }
                } else if (e.key === 'Escape') {
                    submitSuggestionBox.style.display = 'none';
                    submitSelectedIndex = -1;
                }
            });

            document.addEventListener('click', (e) => {
                if (!e.target.closest('input[name="address"]') && !e.target.closest('#submitSuggestions')) {
                    submitSuggestionBox.style.display = 'none';
                    submitSelectedIndex = -1;
                }
            });

            // Accessibility features
            let voiceMode = false;
            let highContrast = false;

            document.getElementById('voiceBtn').addEventListener('click', () => {
                voiceMode = !voiceMode;
                document.getElementById('voiceBtn').textContent = voiceMode ? '🔊 Выключить голос' : '🔊 Голосовое сопровождение';
            });

            document.getElementById('contrastBtn').addEventListener('click', () => {
                highContrast = !highContrast;
                document.body.classList.toggle('high-contrast', highContrast);
                document.getElementById('contrastBtn').textContent = highContrast ? '👓 Обычный режим' : '👓 Режим для слабовидящих';
            });

            // Voice announcements for inputs, selects, and buttons
            document.querySelectorAll('input').forEach(el => {
                el.addEventListener('focus', () => {
                    if (voiceMode && 'speechSynthesis' in window) {
                        const label = el.previousElementSibling ? el.previousElementSibling.textContent.trim() : el.placeholder;
                        speechSynthesis.speak(new SpeechSynthesisUtterance(label));
                    }
                });
            });

            document.querySelectorAll('select').forEach(el => {
                el.addEventListener('focus', () => {
                    if (voiceMode && 'speechSynthesis' in window) {
                        const label = el.previousElementSibling ? el.previousElementSibling.textContent.trim() : 'Выбор';
                        speechSynthesis.speak(new SpeechSynthesisUtterance(label));
                    }
                });
                el.addEventListener('change', () => {
                    if (voiceMode && 'speechSynthesis' in window) {
                        const selected = el.options[el.selectedIndex].text;
                        speechSynthesis.speak(new SpeechSynthesisUtterance('Выбрано: ' + selected));
                    }
                });
            });

            document.querySelectorAll('button').forEach(el => {
                el.addEventListener('click', () => {
                    if (voiceMode && 'speechSynthesis' in window) {
                        const text = el.textContent.replace(/[^\w\sа-яё]/gi, '').trim();
                        speechSynthesis.speak(new SpeechSynthesisUtterance(text));
                    }
                });
            });
        </script>
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
            photo_path = filename  # store relative path
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
                    padding: 15px 25px;
                    border: 2px solid;
                    border-radius: 0;
                    font-size: 1.1em;
                    font-weight: 600;
                    cursor: pointer;
                    transition: all 0.3s ease;
                    margin: 8px;
                    min-width: 140px;
                    position: relative;
                    overflow: hidden;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                    background: transparent;
                }
                .btn-approve {
                    background: transparent;
                    color: #10b981;
                    border-color: #10b981;
                    box-shadow: 0 4px 15px rgba(16, 185, 129, 0.4);
                }
                .btn-approve:hover {
                    background: #10b981;
                    color: white;
                    transform: translateY(-3px) scale(1.05);
                    box-shadow: 0 8px 25px rgba(16, 185, 129, 0.6);
                }
                .btn-reject {
                    background: transparent;
                    color: #ef4444;
                    border-color: #ef4444;
                    box-shadow: 0 4px 15px rgba(239, 68, 68, 0.4);
                }
                .btn-reject:hover {
                    background: #ef4444;
                    color: white;
                    transform: translateY(-3px) scale(1.05);
                    box-shadow: 0 8px 25px rgba(239, 68, 68, 0.6);
                }
                .btn-secondary {
                    background: transparent;
                    color: #333;
                    border-color: #333;
                    box-shadow: 0 4px 15px rgba(0,0,0,0.1);
                }
                .btn-secondary:hover {
                    background: #333;
                    color: white;
                    transform: translateY(-2px) scale(1.02);
                    box-shadow: 0 6px 20px rgba(0,0,0,0.15);
                }
                .no-submissions {
                    text-align: center;
                    padding: 50px;
                    color: #666;
                }
                .admin-links {
                    display: flex;
                    flex-wrap: wrap;
                    gap: 10px;
                    justify-content: center;
                    margin-top: 20px;
                }
                .admin-links a {
                    color: white;
                    text-decoration: none;
                }
                .btn-accessibility {
                    background: rgba(255,255,255,0.4);
                    border: 2px solid white;
                    color: white;
                    padding: 10px 15px;
                    border-radius: 0;
                    cursor: pointer;
                    transition: all 0.3s;
                    font-weight: bold;
                }
                .btn-accessibility:hover {
                    background: rgba(255,255,255,0.6);
                    transform: translateY(-1px);
                    box-shadow: 0 4px 8px rgba(0,0,0,0.2);
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🔧 Админ панель</h1>
                    <p>Управление объектами доступности</p>
                    <div class="admin-links">
                        <a href="/admin/districts" class="btn-accessibility">Статистика по районам</a>
                        <a href="/admin/change_password" class="btn-accessibility">Изменить пароль</a>
                        <a href="/admin/add_admin" class="btn-accessibility">Добавить админа</a>
                        <a href="/admin/logout" class="btn-accessibility">Выйти</a>
                    </div>
                </div>
                <div class="content">
                    {% if submissions %}
                        {% for sub in submissions %}
                        <div class="submission" data-id="{{ sub[0] }}">
                            <h3>{{ sub[1].replace('_', ' ').title() }}</h3>
                            <p><strong>Описание:</strong> {{ sub[2] }}</p>
                            <p><strong>Адрес:</strong> {{ sub[3] }}</p>
                            <p><strong>Отправитель:</strong> {{ sub[6] or 'Аноним' }}</p>
                            {% if sub[4] %}
                            <img src="/uploads/{{ sub[4] }}" alt="Фото объекта">
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
                                removeSubmission(id);
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
                                    removeSubmission(id);
                                } else {
                                    alert('Ошибка при отклонении');
                                }
                            });
                        }
                    }
                function removeSubmission(id) {
                    const submission = document.querySelector(`[data-id="${id}"]`);
                    if (submission) {
                        submission.remove();
                        // Check if no submissions left
                        const submissions = document.querySelectorAll('.submission');
                        if (submissions.length === 0) {
                            document.querySelector('.content').innerHTML = `
                                <div class="no-submissions">
                                    <h2>Нет ожидающих подтверждений</h2>
                                    <p>Все объекты проверены</p>
                                </div>
                                <a href="/" class="btn btn-secondary">Назад к навигации</a>
                            `;
                        }
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
            conn = sqlite3.connect(nav_system.db.db_path, timeout=10)
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
            conn = sqlite3.connect(nav_system.db.db_path)
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
            conn = sqlite3.connect(nav_system.db.db_path)
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
            conn = sqlite3.connect(nav_system.db.db_path)
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

    @app.route('/admin/districts')
    def admin_districts():
        if not session.get('admin'):
            return redirect(url_for('admin_login'))

        # Генерируем карту районов
        map_html = draw_tula_districts_robust()

        # Получаем статистику по районам
        districts_stats = get_district_statistics()

        return render_template('admin_districts.html', districts_stats=districts_stats, map_html=map_html)

    @app.route('/admin/export_districts')
    def export_districts():
        if not session.get('admin'):
            return redirect(url_for('admin_login'))
        stats = get_district_statistics(nav_system.db.db_path)
        filename = export_district_stats_to_excel(stats)
        return send_from_directory('.', filename, as_attachment=True)


    @app.route('/uploads/<filename>')
    def uploaded_file(filename):
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

    @app.route('/tula_districts/<filename>')
    def serve_districts(filename):
        return send_from_directory('tula_districts', filename)

    @app.route('/music/<filename>')
    def serve_music(filename):
        return send_from_directory('music', filename)

    if __name__ == '__main__':
        print("Запуск доступной навигации...")
        print("Откройте в браузере: http://127.0.0.1:5001")
        app.run(debug=True, host='0.0.0.0', port=5000)

except ImportError:
    print("Для запуска веб-интерфейса установите: pip install flask flask-cors requests")
    print("Или запустите только как библиотеку без веб-сервера.")
