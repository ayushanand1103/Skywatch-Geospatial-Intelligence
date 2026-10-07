"""Constant-velocity Kalman filtering and destination ETA estimation."""
from datetime import datetime, timedelta, timezone
from math import asin, atan2, cos, degrees, radians, sin, sqrt

import numpy as np
from geoalchemy2.shape import to_shape

from ..flight_sessions import aircraft_sessions
from ..models import Aircraft

EARTH_RADIUS_M = 6_371_000.0


def _to_xy(lon, lat, origin_lon, origin_lat):
    x = radians(lon - origin_lon) * EARTH_RADIUS_M * cos(radians(origin_lat))
    y = radians(lat - origin_lat) * EARTH_RADIUS_M
    return x, y


def _to_lonlat(x, y, origin_lon, origin_lat):
    lat = origin_lat + degrees(y / EARTH_RADIUS_M)
    lon = origin_lon + degrees(x / (EARTH_RADIUS_M * cos(radians(origin_lat))))
    return lon, lat


def _distance_m(lon1, lat1, lon2, lat2):
    p1, p2 = radians(lat1), radians(lat2)
    dp, dl = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(sqrt(a))


def estimate_eta(db, icao24, destination_lat, destination_lon, hours=24):
    aircraft = db.query(Aircraft).filter(Aircraft.icao24 == icao24.lower()).first()
    if aircraft is None:
        return None
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    sessions = aircraft_sessions(db, aircraft.id, since)
    observations = sessions[-1] if sessions else []
    points = []
    for observation in observations:
        point = to_shape(observation.position)
        item = (observation.created_at, point.x, point.y)
        if not points or item[1:] != points[-1][1:]:
            points.append(item)
    if len(points) < 2:
        raise ValueError('At least two different recorded positions are required for an ETA.')

    origin_lon, origin_lat = points[0][1], points[0][2]
    measurements = [(_to_xy(lon, lat, origin_lon, origin_lat), timestamp) for timestamp, lon, lat in points]
    first_dt = max((measurements[1][1] - measurements[0][1]).total_seconds(), 1.0)
    vx = (measurements[1][0][0] - measurements[0][0][0]) / first_dt
    vy = (measurements[1][0][1] - measurements[0][0][1]) / first_dt
    state = np.array([measurements[0][0][0], measurements[0][0][1], vx, vy], dtype=float)
    covariance = np.diag([10_000.0, 10_000.0, 2_500.0, 2_500.0])
    measurement_matrix = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])
    measurement_noise = np.eye(2) * 2_500.0
    identity = np.eye(4)
    previous_time = measurements[0][1]

    for (mx, my), timestamp in measurements[1:]:
        dt = max((timestamp - previous_time).total_seconds(), 1.0)
        transition = np.array([[1, 0, dt, 0], [0, 1, 0, dt], [0, 0, 1, 0], [0, 0, 0, 1]], dtype=float)
        acceleration_variance = 9.0
        process_noise = acceleration_variance * np.array([
            [dt**4 / 4, 0, dt**3 / 2, 0], [0, dt**4 / 4, 0, dt**3 / 2],
            [dt**3 / 2, 0, dt**2, 0], [0, dt**3 / 2, 0, dt**2],
        ])
        state = transition @ state
        covariance = transition @ covariance @ transition.T + process_noise
        innovation = np.array([mx, my]) - measurement_matrix @ state
        innovation_covariance = measurement_matrix @ covariance @ measurement_matrix.T + measurement_noise
        gain = covariance @ measurement_matrix.T @ np.linalg.inv(innovation_covariance)
        state = state + gain @ innovation
        covariance = (identity - gain @ measurement_matrix) @ covariance
        previous_time = timestamp

    lon, lat = _to_lonlat(state[0], state[1], origin_lon, origin_lat)
    speed = float(sqrt(state[2] ** 2 + state[3] ** 2))
    heading = (degrees(atan2(state[2], state[3])) + 360) % 360
    destination_x, destination_y = _to_xy(destination_lon, destination_lat, lon, lat)
    distance = _distance_m(lon, lat, destination_lon, destination_lat)
    if distance > 0:
        closing_speed = float((state[2] * destination_x + state[3] * destination_y) / distance)
    else:
        closing_speed = speed
    eta_seconds = distance / closing_speed if closing_speed >= 5.0 else None
    eta = previous_time + timedelta(seconds=eta_seconds) if eta_seconds is not None else None
    uncertainty = float(sqrt(max(covariance[0, 0], 0) + max(covariance[1, 1], 0)))
    return {
        'icao24': aircraft.icao24,
        'callsign': aircraft.call_sign,
        'observations': len(points),
        'last_observation': previous_time.isoformat(),
        'estimated_position': {'longitude': lon, 'latitude': lat},
        'destination': {'longitude': destination_lon, 'latitude': destination_lat},
        'filtered_speed_mps': speed,
        'filtered_heading': heading,
        'distance_km': distance / 1000,
        'closing_speed_mps': closing_speed,
        'eta_seconds': eta_seconds,
        'eta': eta.isoformat() if eta else None,
        'position_uncertainty_m': uncertainty,
        'status': 'approaching' if eta else 'not_approaching',
        'method': 'constant_velocity_kalman',
    }
