"""Spatial queries using PostGIS."""
from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Dict, List, Optional
import h3

from geoalchemy2.shape import to_shape
from geoalchemy2 import Geometry
from sqlalchemy import cast, func, text
from sqlalchemy.orm import Session

from .models import Aircraft, AircraftPosition


def get_aircraft_in_viewport(
    db: Session,
    min_lon: float,
    min_lat: float,
    max_lat: float,
    max_lon: float,
    limit: int = 1000,
) -> List[Dict]:
    """Return GeoJSON features for aircraft updated within the last 30 minutes.

    Bounds use the existing argument order: min_lon, min_lat, max_lat, max_lon.
    Viewports crossing the antimeridian are not supported.
    """
    if not (-180 <= min_lon < max_lon <= 180):
        raise ValueError('Longitude bounds must satisfy -180 <= min_lon < max_lon <= 180')
    if not (-90 <= min_lat < max_lat <= 90):
        raise ValueError('Latitude bounds must satisfy -90 <= min_lat < max_lat <= 90')
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
        raise ValueError('limit must be a nonnegative integer')

    # ST_X/ST_Y operate on geometry; the stored column is geography.
    geometry = cast(Aircraft.last_position, Geometry('POINT', srid=4326))
    aircraft_list = db.query(Aircraft).filter(
        func.ST_X(geometry).between(min_lon, max_lon),
        func.ST_Y(geometry).between(min_lat, max_lat),
        Aircraft.last_update >= datetime.now(timezone.utc) - timedelta(minutes=30),
    ).order_by(Aircraft.id).limit(limit).all()

    result = []
    for aircraft in aircraft_list:
        point = to_shape(aircraft.last_position)
        result.append({
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [point.x, point.y]},
            'properties': {
                'icao24': aircraft.icao24,
                'callsign': aircraft.call_sign,
                'origin_country': aircraft.origin_country,
                'altitude': aircraft.altitude_meters,
                'velocity': aircraft.velocity_mps,
                'heading': aircraft.heading_,
                'on_ground': aircraft.on_ground,
                'last_update': aircraft.last_update.isoformat() if aircraft.last_update else None,
            },
        })
    return result

def get_aircraft_near_point(
    db: Session,
    lon: float,
    lat: float,
    radius_km: float,
    limit: int = 100
) -> List[Dict]:
    """
    Find aircraft within radius of a point
    Returns aircraft with distance from center point
    """
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValueError('Coordinates are outside longitude/latitude bounds')
    if not isfinite(radius_km) or radius_km < 0:
        raise ValueError('radius_km must be finite and nonnegative')
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
        raise ValueError('limit must be a nonnegative integer')
    point_wkt = f"SRID=4326;POINT({lon} {lat})"
    radius_meters = radius_km * 1000
    
    # Query with distance calculation 
    query = db.query(
        Aircraft,
        func.ST_Distance(
            Aircraft.last_position,
            func.ST_GeogFromText(point_wkt)
        ).label('distance_meters')
    ).filter(
        func.ST_DWithin(
            Aircraft.last_position,
            func.ST_GeogFromText(point_wkt),
            radius_meters
        ),
        Aircraft.last_update >= datetime.now(timezone.utc) - timedelta(minutes=30)
    ).order_by('distance_meters').limit(limit)
    
    result = []
    for aircraft, distance in query.all():
        if aircraft.last_position:
            point = to_shape(aircraft.last_position)
            coords = [point.x, point.y]
            
            result.append({
                "icao24": aircraft.icao24,
                "callsign": aircraft.call_sign,
                "coordinates": coords,
                "distance_km": round(distance / 1000, 2),
                "altitude": aircraft.altitude_meters,
                "velocity": aircraft.velocity_mps,
                "heading": aircraft.heading_,
                "last_update": aircraft.last_update.isoformat() if aircraft.last_update else None
            })
    
    return result

def get_aircraft_trajectory(
    db: Session,
    icao24: str,
    hours_back: int = 24
) -> Optional[Dict]:
    """
    Get aircraft movement trajectory for last N hours
    Returns GeoJSON LineString
    """
    if not isfinite(hours_back) or hours_back <= 0:
        raise ValueError('hours_back must be finite and positive')
    start_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    
    aircraft = db.query(Aircraft).filter(Aircraft.icao24 == icao24).first()
    if not aircraft:
        return None
    
    positions = db.query(AircraftPosition).filter(
        AircraftPosition.aircraft_id == aircraft.id,
        AircraftPosition.created_at >= start_time
    ).order_by(AircraftPosition.created_at).all()
    
    positions = [pos for pos in positions if pos.position is not None]
    if len(positions) < 2:
        return None
    
    # Build GeoJSON LineString
    coordinates = []
    timestamps = []
    altitudes = []
    
    for pos in positions:
        point = to_shape(pos.position)
        coords = [point.x, point.y]
        coordinates.append(coords)
        timestamps.append(pos.created_at.isoformat())
        altitudes.append(pos.altitude_meters)
    
    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": coordinates
        },
        "properties": {
            "icao24": icao24,
            "callsign": aircraft.call_sign,
            "origin_country": aircraft.origin_country,
            "point_count": len(coordinates),
            "start_time": timestamps[0] if timestamps else None,
            "end_time": timestamps[-1] if timestamps else None,
            "timestamps": timestamps,
            "altitudes": altitudes
        }
    }

# ============= DENSITY ANALYSIS =============

def get_density_heatmap(
    db: Session,
    h3_resolution: int = 7,
    min_count: int = 5
) -> List[Dict]:
    """
    Get aircraft density by H3 hexagons
    Perfect for heatmap visualization
    """
    if isinstance(h3_resolution, bool) or not isinstance(h3_resolution, int) or not 0 <= h3_resolution <= 15:
        raise ValueError('h3_resolution must be an integer from 0 to 15')
    if isinstance(min_count, bool) or not isinstance(min_count, int) or min_count < 1:
        raise ValueError('min_count must be a positive integer')
    # Count position samples, rather than unique aircraft, in the last hour.
    positions = db.query(AircraftPosition).filter(
        AircraftPosition.created_at >= datetime.now(timezone.utc) - timedelta(hours=1),
        AircraftPosition.position.isnot(None),
    ).all()
    cells = {}
    for pos in positions:
        point = to_shape(pos.position)
        cell = h3.latlng_to_cell(point.y, point.x, h3_resolution)
        group = cells.setdefault(cell, {'count': 0, 'altitudes': [], 'velocities': []})
        group['count'] += 1
        if pos.altitude_meters is not None:
            group['altitudes'].append(pos.altitude_meters)
        if pos.velocity_mps is not None:
            group['velocities'].append(pos.velocity_mps)
    result = []
    for cell, group in sorted(cells.items(), key=lambda item: (-item[1]['count'], item[0])):
        if group['count'] >= min_count:
            result.append({
                'h3_cell': cell,
                'count': group['count'],
                'avg_altitude': round(sum(group['altitudes']) / len(group['altitudes']), 2) if group['altitudes'] else None,
                'avg_velocity': round(sum(group['velocities']) / len(group['velocities']), 2) if group['velocities'] else None,
            })
    return result[:1000]

# ============= STATISTICS =============

def get_spatial_stats(db: Session) -> Dict:
    """
    Get comprehensive spatial statistics
    """
    # Total counts
    total_aircraft = db.query(Aircraft).count()
    total_positions = db.query(AircraftPosition).count()
    
    # Recent activity (last hour)
    recent_cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    recent_aircraft = db.query(Aircraft).filter(
        Aircraft.last_update >= recent_cutoff
    ).count()
    
    # Geographic coverage 
    coverage_query = text("""
        SELECT 
            COUNT(DISTINCT origin_country) as countries_covered,
            MIN(ST_Y(last_position::geometry)) as min_lat,
            MAX(ST_Y(last_position::geometry)) as max_lat,
            MIN(ST_X(last_position::geometry)) as min_lon,
            MAX(ST_X(last_position::geometry)) as max_lon
        FROM aircraft
        WHERE last_position IS NOT NULL
    """)
    
    coverage = db.execute(coverage_query).first()
    
    return {
        "total_aircraft": total_aircraft,
        "total_positions": total_positions,
        "active_last_hour": recent_aircraft,
        "countries_covered": coverage.countries_covered if coverage else 0,
        "geographic_bounds": {
            "min_lat": float(coverage.min_lat) if coverage and coverage.min_lat is not None else None,
            "max_lat": float(coverage.max_lat) if coverage and coverage.max_lat is not None else None,
            "min_lon": float(coverage.min_lon) if coverage and coverage.min_lon is not None else None,
            "max_lon": float(coverage.max_lon) if coverage and coverage.max_lon is not None else None
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

# ============= TOP N QUERIES =============

def get_busiest_routes(db: Session, limit: int = 10) -> List[Dict]:
    """
    Group aircraft by callsign prefix; this does not count actual routes or flights.
    total_flights is retained as a compatibility key for aircraft record count.
    """
    query = text("""
        SELECT 
            SUBSTRING(call_sign FROM 1 FOR 3) as airline_code,
            COUNT(DISTINCT icao24) as aircraft_count,
            COUNT(*) as total_flights,
            ARRAY_AGG(DISTINCT origin_country) as countries
        FROM aircraft
        WHERE call_sign IS NOT NULL
          AND call_sign != ''
          AND LENGTH(call_sign) >= 3
        GROUP BY airline_code
        ORDER BY aircraft_count DESC
        LIMIT :limit
    """)
    
    result = db.execute(query, {"limit": limit})
    
    routes = []
    for row in result:
        routes.append({
            "airline_code": row.airline_code,
            "aircraft_count": row.aircraft_count,
            "total_flights": row.total_flights,
            "countries": row.countries
        })
    
    return routes


