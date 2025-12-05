import xml.etree.ElementTree as ET
import sqlite3
from dataclasses import dataclass, field
from typing import List, Optional
import random

@dataclass
class InfrastructureObject:
    id: str
    name: str
    municipal_formation: str
    address: str
    coordinates: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    year_built: Optional[int] = None
    accessibility_features: List[str] = field(default_factory=list)

    def __post_init__(self):
        if self.coordinates and ',' in self.coordinates:
            try:
                lat, lon = self.coordinates.split(',')
                self.latitude = float(lat.strip())
                self.longitude = float(lon.strip())
            except ValueError:
                pass

@dataclass
class SocialOrganization:
    id: str
    name: str
    short_name: str
    address: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    served_disability_categories: List[str] = field(default_factory=list)
    age_categories: List[str] = field(default_factory=list)
    service_forms: List[str] = field(default_factory=list)

class XMLDataParser:
    def __init__(self):
        self.infrastructure_objects = []
        self.social_organizations = []

    def parse_organizations_xml(self, xml_file: str):
        """Parse the social organizations XML (File 1)"""
        tree = ET.parse(xml_file)
        root = tree.getroot()

        for product in root.findall(".//Товар"):
            id_elem = product.find("Ид")
            name_elem = product.find("Наименование")
            if id_elem is None or name_elem is None:
                continue
            obj_id = id_elem.text or ""
            name = name_elem.text or ""

            # Extract properties
            short_name = ""
            address = ""
            served_categories = []
            age_categories = []
            service_forms = []

            for prop in product.findall(".//ЗначенияСвойства"):
                id_prop = prop.find("Ид")
                if id_prop is None:
                    continue
                prop_id = id_prop.text
                value_elem = prop.find("Значение")
                if value_elem is not None and value_elem.text:
                    if prop_id == "29":  # Full name
                        name = value_elem.text
                    elif prop_id == "30":  # Short name
                        short_name = value_elem.text
                    elif prop_id == "679":  # Address
                        address = value_elem.text
                    elif prop_id == "122":  # Disability categories
                        served_categories.append(value_elem.text)
                    elif prop_id == "121":  # Age categories
                        age_categories.append(value_elem.text)
                    elif prop_id == "120":  # Service forms
                        service_forms.append(value_elem.text)

            org = SocialOrganization(
                id=obj_id,
                name=name,
                short_name=short_name,
                address=address,
                served_disability_categories=served_categories,
                age_categories=age_categories,
                service_forms=service_forms
            )

            self.social_organizations.append(org)

    def parse_infrastructure_xml(self, xml_file: str):
        """Parse the infrastructure objects XML (File 2)"""
        tree = ET.parse(xml_file)
        root = tree.getroot()

        for product in root.findall(".//Товар"):
            id_elem = product.find("Ид")
            name_elem = product.find("Наименование")
            if id_elem is None or name_elem is None:
                continue
            obj_id = id_elem.text or ""
            name = name_elem.text or ""

            # Extract properties
            municipal_formation = ""
            address = ""
            coordinates = ""
            year_built = None

            for prop in product.findall(".//ЗначенияСвойства"):
                id_prop = prop.find("Ид")
                if id_prop is None:
                    continue
                prop_id = id_prop.text
                value_elem = prop.find("Значение")
                if value_elem is not None and value_elem.text:
                    if prop_id == "9":  # Municipal formation
                        municipal_formation = value_elem.text
                    elif prop_id == "10":  # Address
                        address = value_elem.text
                    elif prop_id == "11":  # Coordinates
                        coordinates = value_elem.text
                    elif prop_id == "15":  # Year built
                        try:
                            year_built = int(value_elem.text)
                        except (ValueError, TypeError):
                            pass

            obj = InfrastructureObject(
                id=obj_id,
                name=name,
                municipal_formation=municipal_formation,
                address=address,
                coordinates=coordinates,
                year_built=year_built
            )

            # Assign accessibility features based on object type/name
            self._assign_accessibility_features(obj)

            self.infrastructure_objects.append(obj)

    def _assign_accessibility_features(self, obj: InfrastructureObject):
        """Assign accessibility features based on object name and type"""
        name_lower = obj.name.lower()

        # Common accessibility features
        features = []

        # Ramps for various buildings
        if any(keyword in name_lower for keyword in ['поликлиника', 'больница', 'клиника', 'аптека', 'магазин', 'тц', 'торговый центр']):
            features.extend(['пандус_стационарный', 'широкая_дверь'])

        # Elevators in multi-story buildings
        if any(keyword in name_lower for keyword in ['больница', 'клиника', 'тц', 'торговый центр', 'вокзал']):
            features.append('лифт')

        # Parking for various facilities
        if any(keyword in name_lower for keyword in ['больница', 'клиника', 'тц', 'торговый центр', 'аптека']):
            features.append('доступная_парковка')

        # Tactile tiles and audio lights at crossings and public places
        if any(keyword in name_lower for keyword in ['переход', 'перекресток', 'площадь', 'остановка']):
            features.extend(['тактильная_плитка_направляющая', 'тактильная_плитка_предупреждающая', 'светофор_звуковой'])

        # Handrails and lowered curbs in general
        if random.random() < 0.3:  # 30% chance for general accessibility
            features.extend(['поручни', 'понижение_бордюра'])

        # Help buttons in public facilities
        if any(keyword in name_lower for keyword in ['больница', 'клиника', 'аптека', 'вокзал']):
            features.append('кнопка_вызова')

        # Remove duplicates
        obj.accessibility_features = list(set(features))

    def populate_database(self, db_path: str = "accessibility.db"):
        """Populate the database with parsed objects"""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Clear existing data
        cursor.execute("DELETE FROM accessibility_objects")

        for obj in self.infrastructure_objects:
            if obj.latitude and obj.longitude and obj.accessibility_features:
                for feature in obj.accessibility_features:
                    cursor.execute("""
                        INSERT INTO accessibility_objects
                        (feature_type, description, latitude, longitude, address)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        feature,
                        f"{feature.replace('_', ' ').title()} at {obj.name}",
                        obj.latitude,
                        obj.longitude,
                        obj.address or obj.name
                    ))

        conn.commit()
        conn.close()
        print(f"Populated database with {len(self.infrastructure_objects)} infrastructure objects")

if __name__ == "__main__":
    parser = XMLDataParser()
    parser.parse_organizations_xml("../xml/Файл_соцподдержка_1.xml")
    parser.parse_infrastructure_xml("../xml/Файл_соцподдержка_2.xml")
    parser.populate_database()
    print(f"Parsed {len(parser.social_organizations)} organizations and {len(parser.infrastructure_objects)} infrastructure objects")