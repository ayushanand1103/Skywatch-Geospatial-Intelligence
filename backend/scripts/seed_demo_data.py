"""
Populate database with fake aircraft data INCLUDING realistic trajectories
Uses great circle paths between European airports for realism
"""

import random
import math
from datetime import datetime, timezone, timedelta
import argparse
import os
from pathlib import Path
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from app.models import Base

SessionLocal = None
from app import CRUD as crud
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Major European airports as waypoints
EUROPEAN_AIRPORTS = [
    # Italy
    {"name": "Rome FCO", "lat": 41.8003, "lon": 12.2389, "city": "Rome"},
    {"name": "Milan MXP", "lat": 45.6306, "lon": 8.7281, "city": "Milan"},
    {"name": "Venice VCE", "lat": 45.5053, "lon": 12.3519, "city": "Venice"},
    # France
    {"name": "Paris CDG", "lat": 49.0097, "lon": 2.5479, "city": "Paris"},
    {"name": "Nice NCE", "lat": 43.6584, "lon": 7.2159, "city": "Nice"},
    {"name": "Lyon LYS", "lat": 45.7256, "lon": 5.0811, "city": "Lyon"},
    # Germany
    {"name": "Frankfurt FRA", "lat": 50.0379, "lon": 8.5622, "city": "Frankfurt"},
    {"name": "Munich MUC", "lat": 48.3538, "lon": 11.7861, "city": "Munich"},
    {"name": "Berlin BER", "lat": 52.3667, "lon": 13.5033, "city": "Berlin"},
    # Spain
    {"name": "Madrid MAD", "lat": 40.4719, "lon": -3.5626, "city": "Madrid"},
    {"name": "Barcelona BCN", "lat": 41.2974, "lon": 2.0833, "city": "Barcelona"},
    # UK
    {"name": "London LHR", "lat": 51.4700, "lon": -0.4543, "city": "London"},
    {"name": "Manchester MAN", "lat": 53.3537, "lon": -2.2750, "city": "Manchester"},
    # Netherlands
    {"name": "Amsterdam AMS", "lat": 52.3105, "lon": 4.7683, "city": "Amsterdam"},
    # Switzerland
    {"name": "Zurich ZRH", "lat": 47.4647, "lon": 8.5492, "city": "Zurich"},
    # Austria
    {"name": "Vienna VIE", "lat": 48.1103, "lon": 16.5697, "city": "Vienna"},
]

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate distance between two points on Earth using Haversine formula
    Returns distance in kilometers
    """
    R = 6371  # Earth radius in km
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    
    a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    return R * c

def calculate_bearing(lat1, lon1, lat2, lon2):
    """
    Calculate initial bearing (heading) from point 1 to point 2
    Returns bearing in degrees (0-360)
    """
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lon = math.radians(lon2 - lon1)
    
    x = math.sin(delta_lon) * math.cos(lat2_rad)
    y = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(delta_lon)
    
    bearing = math.degrees(math.atan2(x, y))
    return (bearing + 360) % 360

def interpolate_great_circle(lat1, lon1, lat2, lon2, fraction):
    """
    Interpolate a point along great circle path
    fraction: 0.0 (start) to 1.0 (end)
    Returns (lat, lon) of interpolated point
    """
    # Convert to radians
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    # Calculate angular distance
    delta_lat = lat2_rad - lat1_rad
    delta_lon = lon2_rad - lon1_rad
    a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
    angular_distance = 2 * math.asin(math.sqrt(a))
    
    # Handle same points
    if angular_distance < 1e-6:
        return lat1, lon1
    
    # Slerp interpolation
    a_val = math.sin((1 - fraction) * angular_distance) / math.sin(angular_distance)
    b_val = math.sin(fraction * angular_distance) / math.sin(angular_distance)
    
    x = a_val * math.cos(lat1_rad) * math.cos(lon1_rad) + b_val * math.cos(lat2_rad) * math.cos(lon2_rad)
    y = a_val * math.cos(lat1_rad) * math.sin(lon1_rad) + b_val * math.cos(lat2_rad) * math.sin(lon2_rad)
    z = a_val * math.sin(lat1_rad) + b_val * math.sin(lat2_rad)
    
    lat_interp = math.atan2(z, math.sqrt(x**2 + y**2))
    lon_interp = math.atan2(y, x)
    
    return math.degrees(lat_interp), math.degrees(lon_interp)

def generate_altitude_profile(distance_km, num_points):
    """
    Generate realistic altitude profile for flight
    
    Returns list of altitudes in meters
    - Takeoff: climb from 0 to cruise altitude
    - Cruise: maintain altitude
    - Landing: descend to 0
    """
    altitudes = []
    
    # Determine cruise altitude based on distance
    if distance_km < 500:
        cruise_altitude = random.uniform(8000, 10000)  # Short flights
    elif distance_km < 1500:
        cruise_altitude = random.uniform(9000, 11000)  # Medium flights
    else:
        cruise_altitude = random.uniform(10000, 12000)  # Long flights
    
    # Calculate phases
    climb_points = int(num_points * 0.2)  # 20% climbing
    descent_points = int(num_points * 0.2)  # 20% descending
    cruise_points = num_points - climb_points - descent_points  # 60% cruising
    
    # Climb phase (0  cruise altitude)
    for i in range(climb_points):
        fraction = i / climb_points
        # Exponential climb (faster at start, levels off)
        altitude = cruise_altitude * (1 - math.exp(-3 * fraction))
        altitudes.append(altitude + random.uniform(-100, 100))
    
    # Cruise phase (maintain altitude)
    for i in range(cruise_points):
        altitude = cruise_altitude + random.uniform(-200, 200)
        altitudes.append(altitude)
    
    # Descent phase (cruise altitude  0)
    for i in range(descent_points):
        fraction = i / descent_points
        # Exponential descent
        altitude = cruise_altitude * (1 - fraction) ** 2
        altitudes.append(altitude + random.uniform(-100, 100))
    
    return altitudes

def generate_realistic_flight_trajectory(origin_airport, dest_airport, steps=30):
    """
    Generate realistic flight path using great circle route
    
    Args:
        origin_airport: dict with lat, lon, name
        dest_airport: dict with lat, lon, name
        steps: number of position points
        
    Returns list of position dicts with all required fields
    """
    if steps < 2:
        raise ValueError("steps must be at least 2")
    trajectory = []
    
    start_lat = origin_airport["lat"]
    start_lon = origin_airport["lon"]
    end_lat = dest_airport["lat"]
    end_lon = dest_airport["lon"]
    
    # Calculate total distance
    distance_km = haversine_distance(start_lat, start_lon, end_lat, end_lon)
    
    # Generate altitude profile
    altitudes = generate_altitude_profile(distance_km, steps)
    
    # Calculate flight time (based on average speed ~800 km/h)
    avg_speed_kmh = 800
    total_time_hours = distance_km / avg_speed_kmh
    time_per_step = total_time_hours * 60 / (steps - 1)  # minutes per step
    
    # Starting time (1 hour ago)
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=total_time_hours)
    
    for i in range(steps):
        fraction = i / (steps - 1) if steps > 1 else 0
        
        # Interpolate position along great circle
        lat, lon = interpolate_great_circle(start_lat, start_lon, end_lat, end_lon, fraction)
        
        # Calculate heading (bearing to next point)
        if i < steps - 1:
            next_fraction = (i + 1) / (steps - 1)
            next_lat, next_lon = interpolate_great_circle(start_lat, start_lon, end_lat, end_lon, next_fraction)
            heading = calculate_bearing(lat, lon, next_lat, next_lon)
        else:
            # Last point uses previous heading
            heading = calculate_bearing(
                trajectory[-1]['latitude'],
                trajectory[-1]['longitude'],
                lat, lon
            ) if trajectory else 0
        
        # Get altitude from profile
        altitude = altitudes[i]
        
        # Calculate realistic speed based on altitude
        # Lower altitude = slower speed (takeoff/landing)
        # Higher altitude = faster speed (cruise)
        altitude_factor = min(1.0, altitude / 10000)  # Normalize by cruise altitude
        speed_kmh = 400 + (400 * altitude_factor)  # 400-800 km/h range
        speed_mps = speed_kmh / 3.6
        
        # Vertical rate (m/s) - positive climbing, negative descending
        if i > 0:
            altitude_change = altitude - altitudes[i-1]
            time_delta_seconds = time_per_step * 60
            vertical_rate = altitude_change / time_delta_seconds if time_delta_seconds > 0 else 0
        else:
            vertical_rate = 0
        
        # On ground only at start/end if altitude is very low
        on_ground = altitude < 100
        
        # Time progression
        current_time = start_time + (end_time - start_time) * fraction
        
        trajectory.append({
            'latitude': lat,
            'longitude': lon,
            'altitude': max(0, altitude),  # Never negative
            'timestamp': current_time,
            'velocity': speed_mps,
            'heading': heading,
            'vertical_rate': vertical_rate,
            'on_ground': on_ground
        })
    
    return trajectory

def generate_test_aircraft_with_trajectories(count=100):
    """Generate fake aircraft with realistic great circle trajectories"""
    aircraft_list = []
    
    countries = ["Italy", "France", "Germany", "Spain", "United Kingdom", 
                 "Netherlands", "Switzerland", "Austria"]
    airlines = ["AZA", "AFR", "DLH", "IBE", "BAW", "RYR", "EZY", "SWR", "AUA"]
    
    for i in range(count):
        # Pick random origin and destination airports (different)
        origin = random.choice(EUROPEAN_AIRPORTS)
        dest = random.choice([a for a in EUROPEAN_AIRPORTS if a != origin])
        
        # Generate realistic trajectory between airports
        trajectory = generate_realistic_flight_trajectory(origin, dest, steps=30)
        
        aircraft_data = {
            'icao24': f"DEMO-{uuid4().hex[:12]}",
            'callsign': f"{random.choice(airlines)}{random.randint(100, 9999)}",
            'origin_country': random.choice(countries),
            'on_ground': False,
            'trajectory': trajectory,
            'origin': origin['name'],
            'destination': dest['name']
        }
        
        aircraft_list.append(aircraft_data)
    
    return aircraft_list

def populate_database_with_trajectories(count=100):
    """Populate database with aircraft + their trajectories"""
    logger.info(f" Generating {count} aircraft with GREAT CIRCLE trajectories...")
    aircraft_list = generate_test_aircraft_with_trajectories(count)
    
    if SessionLocal is None:
        raise RuntimeError("Configure a demo database before seeding")
    db = SessionLocal()
    try:
        stored_aircraft = 0
        stored_positions = 0
        errors = 0
        
        for aircraft_data in aircraft_list:
            try:
                # Use CURRENT position (random point in trajectory, not landing!)
                # This gives variety in altitudes instead of all aircraft landed
                trajectory_length = len(aircraft_data['trajectory'])
                current_position_idx = trajectory_length - 1
                current = aircraft_data['trajectory'][current_position_idx]
                
                logger.info(f"    {aircraft_data['callsign']}: {aircraft_data['origin']}  {aircraft_data['destination']} (alt: {current['altitude']:.0f}m)")
                
                # Get/create aircraft with complete data
                aircraft = crud.get_or_create_aircraft(
                    db, 
                    aircraft_data['icao24'],
                    {
                        'callsign': aircraft_data['callsign'],
                        'origin_country': aircraft_data['origin_country'],
                        'on_ground': current['on_ground'],
                        'latitude': current['latitude'],
                        'longitude': current['longitude'],
                        'altitude': current['altitude'],
                        'velocity': current['velocity'],
                        'heading': current['heading'],
                        'vertical_rate': current.get('vertical_rate', 0),
                        'last_update': current['timestamp'],
                        'timestamp': current['timestamp']
                    }
                )
                stored_aircraft += 1
                
                # Store all trajectory points
                for point in aircraft_data['trajectory']:
                    position_data = {
                        'latitude': point['latitude'],
                        'longitude': point['longitude'],
                        'altitude': point['altitude'],
                        'velocity': point['velocity'],
                        'heading': point['heading'],
                        'vertical_rate': point['vertical_rate'],
                        'on_ground': point['on_ground'],
                        'timestamp': point['timestamp']
                    }
                    
                    crud.create_aircraft_position(db, aircraft.id, position_data)
                    stored_positions += 1
                
                # Aircraft already has current position from above, just commit
                db.commit()
                
            except Exception as e:
                logger.error(f" Error storing aircraft {aircraft_data['icao24']}: {e}")
                import traceback
                traceback.print_exc()
                db.rollback()
                errors += 1
                continue
        
        logger.info("=" * 60)
        logger.info(f" Stored {stored_aircraft} aircraft")
        logger.info(f" Stored {stored_positions} positions")
        if stored_aircraft > 0:
            logger.info(f"   Average: {stored_positions // stored_aircraft} points per aircraft")
        if errors > 0:
            logger.warning(f"  {errors} errors")
        logger.info("=" * 60)
        
        # Verify database stats
        stats = crud.get_stats(db)
        logger.info(f" Total in database:")
        logger.info(f"   Aircraft: {stats['total_aircraft']}")
        logger.info(f"   Positions: {stats['total_aircraft_positions']}")
        
        return {
            'stored_aircraft': stored_aircraft,
            'stored_positions': stored_positions,
            'errors': errors
        }
        
    except Exception as e:
        logger.error(f" Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return None
        
    finally:
        db.close()

def main():
    parser = argparse.ArgumentParser(description='Seed a separate demo database with synthetic aircraft.')
    parser.add_argument('--count', type=int, default=100)
    args = parser.parse_args()
    if args.count < 1:
        parser.error('--count must be positive')
    load_dotenv(Path(__file__).resolve().parents[1] / '.env')
    demo_url = os.getenv('DEMO_DATABASE_URL')
    live_url = os.getenv('DATABASE_URL')
    if not demo_url:
        parser.error('Set DEMO_DATABASE_URL to an existing, separate PostgreSQL/PostGIS database')
    demo = make_url(demo_url)
    if not demo.database or not demo.database.endswith('_demo'):
        parser.error('Demo database name must end in _demo')
    if live_url and demo.database == make_url(live_url).database:
        parser.error('Demo database must have a different name from the app database')
    engine = create_engine(demo_url)
    global SessionLocal
    SessionLocal = sessionmaker(bind=engine)
    try:
        Base.metadata.create_all(engine)
        result = populate_database_with_trajectories(args.count)
        return 0 if result and not result['errors'] else 1
    finally:
        engine.dispose()


if __name__ == '__main__':
    raise SystemExit(main())
