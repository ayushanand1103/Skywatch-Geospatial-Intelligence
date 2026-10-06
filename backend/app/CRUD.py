from turtle import position

from sqlalchemy.orm import Session
from geoalchemy2.functions import ST_Distance, ST_Transform,ST_Point,ST_DWithin
from geoalchemy2.elements import WKTElement
import h3
from datetime import datetime, timezone
from typing import List, Optional
from models import Aircraft, AircraftPosition, Vessel,VesselPosition,events,Alert
from geoalchemy2.shape import from_shape , to_shape
from shapely.geometry import Point
from services import anomaly_detection
from geoalchemy2.shape import from_shape
from shapely.geometry import Point

## Aircraft CRUD operations

def get_or_create_aircraft(db: Session, icao24: str, data: dict):
    """
    Get an existing aircraft
    or create a new one if it doesn't exist.
    Update the last position of aircraft if it exists.
    """
    aircraft = db.query(Aircraft).filter(Aircraft.icao24 == icao24).first()
    if aircraft:
        aircraft.call_sign = data.get("call_sign")
        aircraft.origin_country = data.get("origin_country")
        aircraft.last_update = data.get("last_update")
        aircraft.altitude_meters = data.get("altitude_meters")
        aircraft.velocity_mps = data.get("velocity_mps")
        aircraft.heading_ = data.get("heading_")
        aircraft.on_ground = data.get("on_ground")
        if data.get("longitude") and data.get("latitude"):
            point = f"POINT({data['longitude']} {data['latitude']})"
            aircraft.last_position = WKTElement(point, srid=4326)

        else :
            ##Create a new aircraft if it doesn't exist
            # Create new aircraft
            point = f"POINT({data['longitude']} {data['latitude']})"
            aircraft = Aircraft(
            icao24=icao24,
            callsign=data.get('callsign'),
            origin_country=data.get('origin_country'),
            last_position=WKTElement(point, srid=4326),
            last_update=data.get('last_update'),
            altitude_meters=data.get('altitude'),
            velocity_mps=data.get('velocity'),
            heading=data.get('heading'),
            on_ground=data.get('on_ground')
        )
        db.add(aircraft)
    
        db.commit()
        db.refresh(aircraft)
        return aircraft

    def create_aircraft_position(db:Session,aircraft_id:int,data:dict):
        """
        Record aircraft position in the histrory
        Calculate the H3 cell ID for the position and store it in the database.
        """
        lon , lat = data.get("longitude") , data.get("latitude")

        #Calculate H3 cell ID for the position
        try:
            h3_cell = h3.latlng_to_cell(lat,lon,res=7)
        except Exception as e:
            h3_cell = h3.geo_to_h3(lat,lon,resolution=7)

        shapely_point = Point(lon,lat)
        geog_point = from_shape(shapely_point,srid=4326)

        position = AircraftPosition(
        aircraft_id=aircraft_id,
        position=geog_point,  
        timestamp=data.get('timestamp', datetime.now(timezone.utc)),
        altitude_meters=data.get('altitude'),
        velocity_mps=data.get('velocity'),
        heading=data.get('heading'),
        h3_cell_id=h3_cell
    )
    
        db.add(position)
        db.commit()
        db.refresh(position)
        
        return position


    

            
