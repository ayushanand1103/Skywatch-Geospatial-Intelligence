from datetime import datetime, timezone
from typing import List

import h3
from sqlalchemy import cast
from sqlalchemy.orm import Session
from geoalchemy2 import Geography, Geometry
from geoalchemy2.elements import WKTElement
from geoalchemy2.functions import ST_DWithin, ST_Within
from geoalchemy2.shape import to_shape

from .models import Aircraft, AircraftPosition, Vessel, events, Alert
from .services.anomaly_detection import AnomalyDetector


def _point(data):
    lon, lat = data.get('longitude'), data.get('latitude')
    if lon is None or lat is None:
        raise ValueError('longitude and latitude are required')
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValueError('Coordinates are outside longitude/latitude bounds')
    return WKTElement(f'POINT({lon} {lat})', srid=4326)


def _save(db, record):
    try:
        db.add(record)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(record)
    return record


def get_or_create_aircraft(db: Session, icao24: str, data: dict):
    aircraft = get_aircraft_by_icao24(db, icao24)
    if aircraft is None:
        aircraft = Aircraft(icao24=icao24)
    fields = {
        'call_sign': ('call_sign', 'callsign'),
        'aircraft_type': ('aircraft_type',),
        'origin_country': ('origin_country',),
        'last_update': ('last_update',),
        'altitude_meters': ('altitude_meters', 'altitude'),
        'velocity_mps': ('velocity_mps', 'velocity'),
        'heading_': ('heading_', 'heading'),
        'on_ground': ('on_ground',),
    }
    for attribute, keys in fields.items():
        for key in keys:
            if key in data:
                setattr(aircraft, attribute, data[key])
                break
    if data.get('longitude') is not None and data.get('latitude') is not None:
        aircraft.last_position = _point(data)
    return _save(db, aircraft)


def create_aircraft_position(db: Session, aircraft_id: int, data: dict):
    point = _point(data)
    position = AircraftPosition(
        aircraft_id=aircraft_id,
        position=point,
        created_at=data.get('timestamp') or datetime.now(timezone.utc),
        altitude_meters=data.get('altitude_meters', data.get('altitude')),
        velocity_mps=data.get('velocity_mps', data.get('velocity')),
        heading_=data.get('heading_', data.get('heading')),
        h3_cell_id=h3.latlng_to_cell(data['latitude'], data['longitude'], 7),
    )
    return _save(db, position)


def get_aircraft_in_bbox(db: Session, min_lat: float, min_lon: float,
                         max_lat: float, max_lon: float, limit: int = 1000) -> List[Aircraft]:
    bbox = WKTElement(
        f'POLYGON(({min_lon} {min_lat}, {max_lon} {min_lat}, '
        f'{max_lon} {max_lat}, {min_lon} {max_lat}, {min_lon} {min_lat}))',
        srid=4326,
    )
    return db.query(Aircraft).filter(
        ST_Within(cast(Aircraft.last_position, Geometry('POINT', srid=4326)), bbox)
    ).limit(limit).all()


def get_aircraft_near_point(db: Session, lon: float, lat: float,
                            radius_km: float, limit: int = 100) -> List[Aircraft]:
    if radius_km < 0:
        raise ValueError('radius_km must be nonnegative')
    point = _point({'longitude': lon, 'latitude': lat})
    return db.query(Aircraft).filter(
        ST_DWithin(Aircraft.last_position, cast(point, Geography('POINT', srid=4326)),
                   radius_km * 1000)
    ).limit(limit).all()


def get_aircraft_trajectory(db: Session, aircraft_id: int, start_time: datetime,
                            end_time: datetime) -> List[AircraftPosition]:
    # The current model stores observation time in created_at.
    return db.query(AircraftPosition).filter(
        AircraftPosition.aircraft_id == aircraft_id,
        AircraftPosition.created_at >= start_time,
        AircraftPosition.created_at <= end_time,
    ).order_by(AircraftPosition.created_at).all()


def get_aircraft_by_icao24(db: Session, icao24: str):
    return db.query(Aircraft).filter(Aircraft.icao24 == icao24).first()


def get_aircraft_positions_since(db: Session, aircraft_id: int, since: datetime,
                                 limit: int = 1000):
    return db.query(AircraftPosition).filter(
        AircraftPosition.aircraft_id == aircraft_id,
        AircraftPosition.created_at >= since,
    ).order_by(AircraftPosition.created_at.asc()).limit(limit).all()


def get_stats(db: Session) -> dict:
    return {
        'total_aircraft': db.query(Aircraft).count(),
        'total_vessels': db.query(Vessel).count(),
        'total_events': db.query(events).count(),
        'total_aircraft_positions': db.query(AircraftPosition).count(),
    }


def calculate_alert_priority(alert_data: dict):
    # Preserve detector priorities; otherwise use the model default.
    return alert_data.get('priority', 50)


def create_alert(db: Session, alert_data: dict):
    alert = Alert(
        alert_type=alert_data['type'],
        severity=alert_data['severity'],
        reason=alert_data['reason'],
        aircraft_icao24=alert_data.get('aircraft_icao24', alert_data.get('icao24')),
        aircraft_callsign=alert_data.get('aircraft_callsign', alert_data.get('callsign')),
        aircraft_id=alert_data.get('aircraft_id'),
        position=_point(alert_data),
        detected_at=datetime.now(timezone.utc),
        is_active=True,
        is_acknowledged=False,
        details=alert_data.get('details', {}),
        priority=calculate_alert_priority(alert_data),
    )
    return _save(db, alert)


def get_active_alerts(db: Session, limit: int = 100):
    return db.query(Alert).filter(Alert.is_active.is_(True)).order_by(
        Alert.priority.desc(), Alert.detected_at.desc()
    ).limit(limit).all()


def get_alerts_by_severity(db: Session, severity: str, limit: int = 100):
    return db.query(Alert).filter(
        Alert.severity == severity, Alert.is_active.is_(True)
    ).order_by(Alert.detected_at.desc()).limit(limit).all()


def get_alerts_for_aircraft(db: Session, icao24: str, limit: int = 50):
    return db.query(Alert).filter(Alert.aircraft_icao24 == icao24).order_by(
        Alert.detected_at.desc()
    ).limit(limit).all()


def acknowledge_alert(db: Session, alert_id: int):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if alert:
        alert.is_acknowledged = True
        return _save(db, alert)
    return None


def resolve_alert(db: Session, alert_id: int):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if alert:
        alert.is_active = False
        alert.resolved_at = datetime.now(timezone.utc)
        return _save(db, alert)
    return None

def run_anomaly_detection_on_all_aircraft(db: Session):
    """
    Run anomaly detection on all aircraft and create alerts
    Includes intelligent deduplication to avoid duplicate alerts
    
    Returns:
        list[Alert]: List of newly created alerts (excludes updated existing ones)
    """
    # ============= STEP 1: Get all aircraft with positions =============
    aircraft = db.query(Aircraft).filter(Aircraft.last_position.isnot(None)).all()
    
    if not aircraft:
        return []
    
    # ============= STEP 2: Prepare data for detector =============
    aircraft_data = []
    for a in aircraft:
        if a.last_position:
            # Extract lat/lon from Geography field
            point = to_shape(a.last_position)
            
            aircraft_data.append({
                'icao24': a.icao24,
                'callsign': a.call_sign,
                'latitude': point.y,   # point.y = latitude
                'longitude': point.x,  # point.x = longitude
                'altitude': a.altitude_meters if a.altitude_meters else 0,
                'velocity': a.velocity_mps if a.velocity_mps else 0,
                'vertical_rate': a.vertical_rate if hasattr(a, 'vertical_rate') else 0,
                'heading': a.heading_ if a.heading_ is not None else 0
            })
    
    if not aircraft_data:
        return []
    
    # ============= STEP 3: Run anomaly detection =============
    detector = AnomalyDetector()
    detected_anomalies = detector.detect_all(aircraft_data)
    
    # ============= STEP 4: Create/update alerts with deduplication =============
    new_alerts = []
    updated_count = 0
    
    for anomaly in detected_anomalies:
        # check if alert already exists (same aircraft + same type + still active)
        existing_alert = db.query(Alert).filter(
            Alert.aircraft_icao24 == anomaly['icao24'],
            Alert.alert_type == anomaly['type'],
            Alert.is_active == True
        ).first()
        
        if existing_alert:
            # update existing alert timestamp (anomaly still ongoing)
            existing_alert.detected_at = datetime.now(timezone.utc)
            # Optionally update position if aircraft moved
            existing_alert.position = _point(anomaly)
            existing_alert.severity = anomaly['severity']
            existing_alert.reason = anomaly['reason']
            existing_alert.details = anomaly.get('details', {})
            existing_alert.priority = calculate_alert_priority(anomaly)
            existing_alert.aircraft_callsign = anomaly.get('callsign')
            updated_count += 1
        else:
            # create new alert only if doesn't exist
            alert = Alert(
                alert_type=anomaly['type'],
                severity=anomaly['severity'],
                reason=anomaly['reason'],
                aircraft_icao24=anomaly['icao24'],
                aircraft_callsign=anomaly['callsign'],
                position=_point(anomaly),
                detected_at=datetime.now(timezone.utc),
                is_active=True,
                is_acknowledged=False,
                priority=anomaly['priority'],
                details=anomaly.get('details', {})
            )
            db.add(alert)
            new_alerts.append(alert)
    
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    
    # Log summary
    if new_alerts or updated_count > 0:
        print(f" Created {len(new_alerts)} new alerts, updated {updated_count} existing")
    
    return new_alerts


# ============= Auto-resolve alerts =============

def auto_resolve_old_alerts(db: Session, max_age_minutes=30):
    """
    Automatically resolve alerts that haven't been updated in N minutes
    (means aircraft left restricted zone or anomaly stopped)
    
    Call this periodically or at the end of detection run
    """
    from datetime import timedelta
    
    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
    
    old_alerts = db.query(Alert).filter(
        Alert.is_active == True,
        Alert.detected_at < cutoff_time
    ).all()
    
    for alert in old_alerts:
        alert.is_active = False
        alert.resolved_at = datetime.now(timezone.utc)
    
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    
    if old_alerts:
        print(f"Auto-resolved {len(old_alerts)} old alerts")
    
    return len(old_alerts)

  
def get_alert_statistics(db: Session):
    """Get alert stats for dashboard"""
    return {
        'total_alerts': db.query(Alert).count(),
        'active_alerts': db.query(Alert).filter(Alert.is_active == True).count(),
        'by_severity': {
            'HIGH': db.query(Alert).filter(Alert.severity == 'HIGH', Alert.is_active == True).count(),
            'MEDIUM': db.query(Alert).filter(Alert.severity == 'MEDIUM', Alert.is_active == True).count(),
            'LOW': db.query(Alert).filter(Alert.severity == 'LOW', Alert.is_active == True).count()
        },
        'by_type': {
            'SPEED_ANOMALY': db.query(Alert).filter(Alert.alert_type == 'SPEED_ANOMALY', Alert.is_active == True).count(),
            'ALTITUDE_ANOMALY': db.query(Alert).filter(Alert.alert_type == 'ALTITUDE_ANOMALY', Alert.is_active == True).count(),
            'GEOFENCE_VIOLATION': db.query(Alert).filter(Alert.alert_type == 'GEOFENCE_VIOLATION', Alert.is_active == True).count(),
        }
    }
