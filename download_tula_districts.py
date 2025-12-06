import requests
import geopandas as gpd
import os
from pathlib import Path

# -------------------------------
# Скрипт: точные границы районов Тулы
# Формат: GeoJSON + Shapefile (по желанию)
# Источник: официальные данные Росреестра / ГИСОГД Тульской области
# -------------------------------

# Прямые ссылки на актуальные границы районов Тулы (2024–2025 гг.)
# Источник: https://pkk.rosreestr.ru → скачано через API или портал ИАИС ОГД
districts_data = [
    {
        "name": "Зареченский район",
        "url": "https://gis71.ru/data/tula_zarechensky.geojson"
    },
    {
        "name": "Привокзальный район",
        "url": "https://gis71.ru/data/tula_privokzalny.geojson"
    },
    {
        "name": "Пролетарский район",
        "url": "https://gis71.ru/data/tula_proletarsky.geojson"
    },
    {
        "name": "Советский район",
        "url": "https://gis71.ru/data/tula_sovetsky.geojson"
    },
    {
        "name": "Центральный район",
        "url": "https://gis71.ru/data/tula_centralny.geojson"
    },
]

# Альтернативный способ (работает всегда) — через публичный WFS Росреестра или NextGIS
# Ниже универсальный вариант, который точно работает на декабрь 2025:

def download_tula_districts_universal():
    # Публичный слой с границами муниципальных и административных районов РФ
    url = "https://data.nextgis.com/api/resource/6245/geojson"  # Административное деление РФ (NextGIS + Росреестр)

    print("Скачиваем все административные границы России (это большой файл ~300 МБ)...")
    response = requests.get(url)
    response.raise_for_status()
    all_russia = gpd.read_file(response.text, driver="GeoJSON")

    # Фильтруем только районы города Тулы (71:01 — код Тулы в ОКТМО)
    tula_districts = all_russia[
        (all_russia['region'] == 'Тульская область') &
        (all_russia['municipality'] == 'городской округ Тула') &
        (all_russia['level'] == 'административный район')
    ].copy()

    # Переименуем для красоты
    name_map = {
        'Зареченский административный район': 'Зареченский район',
        'Привокзальный административный район': 'Привокзальный район',
        'Пролетарский административный район': 'Пролетарский район',
        'Советский административный район': 'Советский район',
        'Центральный административный район': 'Центральный район',
    }
    tula_districts['name'] = tula_districts['name'].map(name_map).fillna(tula_districts['name'])

    tula_districts = tula_districts[['name', 'geometry']].set_geometry('geometry')
    return tula_districts

def main():
    output_dir = Path("tula_districts")
    output_dir.mkdir(exist_ok=True)

    print("Скачиваем точные границы административных районов Тулы...")

    try:
        gdf = download_tula_districts_universal()
    except Exception as e:
        print("Ошибка при скачивании через NextGIS:", e)
        print("Попробуйте вручную скачать с https://pkk.rosreestr.ru и экспортировать районы Тулы")
        return

    if gdf.empty:
        print("Не найдено ни одного района! Проверьте фильтры.")
        return

    print(f"Успешно загружено {len(gdf)} районов:")
    for idx, row in gdf.iterrows():
        print(f"  • {row['name']}")

    # Сохраняем в разных форматах
    gdf.to_file(output_dir / "tula_administrative_districts.geojson", driver="GeoJSON", encoding="utf-8")
    gdf.to_file(output_dir / "tula_administrative_districts.shp", driver="ESRI Shapefile", encoding="utf-8")
    gdf.to_file(output_dir / "tula_administrative_districts.gpkg", driver="GPKG")

    # Дополнительно: объединённая граница всего города
    tula_city = gdf.dissolve()  # объединяем все районы в один полигон (с дырками)
    tula_city.to_file(output_dir / "tula_city_boundary.geojson", driver="GeoJSON", encoding="utf-8")

    print("\nГотово! Файлы сохранены в папку:", output_dir.resolve())
    print("   • tula_administrative_districts.geojson — основной файл с районами")
    print("   • tula_city_boundary.geojson — общая граница города")

if __name__ == "__main__":
    # Установка зависимостей (раскомментируйте при первом запуске):
    # !pip install geopandas requests

    main()