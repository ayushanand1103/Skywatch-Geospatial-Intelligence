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

def get_aircraft_in_bbox(db:Session,min_lat:float,min_lon:float,max_lat:float,max_lon:float,limit:int=1000)->List[Aircraft]:
        """
        Get all aircraft within a bounding box defined by min and max lat/lon.
        """
        bbox = f"POLYGON(({min_lon} {min_lat}, {max_lon} {min_lat}, " \
           f"{max_lon} {max_lat}, {min_lon} {max_lat}, {min_lon} {min_lat}))"
    
        aircraft = db.query(Aircraft).filter(
        Aircraft.last_position.ST_Within(WKTElement(bbox, srid=4326))
        ).limit(limit).all()
    
        return aircraft

def get_aircraft_near_point(db:Session,lon:float,lat:float,radius_km:float,limit:int=100)-> List[Aircraft]:
        """Get aircrafts within a radius"""
        point = WKTElement(f"POINT({lon} {lat})", srid=4326)
        radius_meters = radius_km * 1000
    
        aircraft = db.query(Aircraft).filter(
            ST_DWithin(Aircraft.last_position, point, radius_meters)
        ).limit(limit).all()
        
        return aircraft

def get_aircraft_trajectory(db:Session,aircraft_id:int,start_time:datetime,end_time:datetime)->List[Aircraft]:
        """Get aircraft position history for time range"""
        positions = db.query(AircraftPosition).filter(
        AircraftPosition.aircraft_id == aircraft_id,
        AircraftPosition.timestamp >= start_time,
        AircraftPosition.timestamp <= end_time
    )   .order_by(AircraftPosition.timestamp).all()
    
        return positions

def get_aircraft_by_icao24(db: Session, icao24: str):
    """Get aircraft by ICAO24 identifier"""
    return db.query(Aircraft).filter(Aircraft.icao24 == icao24).first()

def get_aircraft_positions_since(db: Session, aircraft_id: int, since: datetime, limit: int = 1000):
    """Get aircraft positions since specific time"""
    return (
        db.query(AircraftPosition)
        .filter(
            AircraftPosition.aircraft_id == aircraft_id,
            AircraftPosition.timestamp >= since
        )
        .order_by(AircraftPosition.timestamp.asc())
        .limit(limit)
        .all()

##Utility functions

def get_stats(db: Session) -> dict:
    """Get platform statistics"""
    total_aircraft = db.query(Aircraft).count()
    total_vessels = db.query(Vessel).count()
    total_events = db.query(Event).count()
    total_aircraft_positions = db.query(AircraftPosition).count()
    
    return {
        "total_aircraft": total_aircraft,
        "total_vessels": total_vessels,
        "total_events": total_events,
        "total_aircraft_positions": total_aircraft_positions
    }

##Alert CRUD operations
def create_alert(db: Session , alert_data:dict):
    """Create a new alert in database"""
    point = f"POINT({alert_data['longitude']} {alert_data['latitude']})"
    priority = calculate_alert_priority(alert_data)
    alert = Alert(
        alert_type=alert_data['type'],
        severity=alert_data['severity'],
        reason=alert_data['reason'],
        aircraft_icao24=alert_data['aircraft_icao24'],
        aircraft_callsign=alert_data['aircraft_callsign'],
        position=WKTElement(point, srid=4326),
        detected_at=datetime.now(timezone.utc),
        is_active=True,
        is_acknowledged=False,
        details=alert_data.get('details', {}),
        priority=priority
    )
    
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert

    def get_active_alerts(db: Session, limit: int = 100):
    """Get all active alerts"""
    return (
        db.query(Alert)
        .filter(Alert.is_active == True)
        .order_by(Alert.priority.desc(), Alert.detected_at.desc())
        .limit(limit)
        .all()
    )

def get_alerts_by_severity(db: Session, severity: str, limit: int = 100):
    """Get alerts by severity level"""
    return (
        db.query(Alert)
        .filter(Alert.severity == severity, Alert.is_active == True)
        .order_by(Alert.detected_at.desc())
        .limit(limit)
        .all()
    )

def get_alerts_for_aircraft(db: Session, icao24: str, limit: int = 50):
    """Get all alerts for specific aircraft"""
    return (
        db.query(Alert)
        .filter(Alert.aircraft_icao24 == icao24)
        .order_by(Alert.detected_at.desc())
        .limit(limit)
        .all()
    )

def acknowledge_alert(db: Session, alert_id: int):
    """Mark alert as acknowledged"""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if alert:
        alert.is_acknowledged = True
        db.commit()
        db.refresh(alert)
    return alert

def resolve_alert(db: Session, alert_id: int):
    """Mark alert as resolved"""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if alert:
        alert.is_active = False
        alert.resolved_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(alert)
    return alert





            
