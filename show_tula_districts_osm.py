import osmnx as ox
import geopandas as gpd
import folium
from shapely.geometry import Polygon
from folium.features import GeoJsonTooltip

# Название места — можно писать "Тула, Russia" или "Tula, Russia"
PLACE_NAME = "Тула, Russia"

# 1) Получаем геометрию города (outline)
print("Запрашиваю геометрию города...")
gdf_place = ox.geocode_to_gdf(PLACE_NAME)

# 2) Получаем relations с административными границами внутри полигона города.
#    Мы запрашиваем объекты с boundary=administrative и admin_level (попробуем несколько уровней).
tags = {"boundary": "administrative"}

# ОSMnx умеет брать по bbox/полигонам - возьмём bbox города
bbox = gdf_place.total_bounds  # [minx, miny, maxx, maxy]
north, south, east, west = bbox[3], bbox[1], bbox[2], bbox[0]
# osmnx.geometries_from_bbox(ymax, ymin, xmax, xmin, tags)
print("Запрашиваю административные границы внутри bbox города через OSM...")
try:
    adm = ox.geometries_from_bbox(north, south, east, west, tags)
except Exception as e:
    raise RuntimeError("Ошибка при запросе OSM: " + str(e))

# Фильтруем по полигонам (и по наличию имени)
polygons = adm[adm.geometry.type.isin(['Polygon','MultiPolygon'])].copy()
if polygons.empty:
    print("Не найдено полигонов в результате — попробуйте другой запрос/источник")
else:
    # приводим к EPSG:4326
    polygons = polygons.to_crs(epsg=4326)
    center = polygons.unary_union.centroid
    m = folium.Map(location=[center.y, center.x], zoom_start=11, tiles="cartodbpositron")
    tooltip_fields = ['name'] if 'name' in polygons.columns else []
    tooltip = GeoJsonTooltip(fields=tooltip_fields,
                             aliases=['Район:'] if tooltip_fields else [],
                             localize=True)

    folium.GeoJson(
        polygons,
        name="Адм. районы OSM",
        tooltip=tooltip,
        highlight_function=lambda feat: {"weight":3, "color":"green"}
    ).add_to(m)
    folium.LayerControl().add_to(m)
    m.save("tula_districts_osm_map.html")
    print("Готово: откройте tula_districts_osm_map.html")

    # Print polygons for districts
    for idx, row in polygons.iterrows():
        name = row.get('name', 'Unknown')
        if 'район' in name.lower() or 'district' in name.lower():
            geom = row.geometry
            if geom.type == 'Polygon':
                coords = list(geom.exterior.coords)
                print(f"District: {name}")
                print(f"Polygon: {coords}")
            elif geom.type == 'MultiPolygon':
                for i, poly in enumerate(geom):
                    coords = list(poly.exterior.coords)
                    print(f"District: {name} (part {i})")
                    print(f"Polygon: {coords}")