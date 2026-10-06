"""
Anomaly detection service module
Anomaly Detection Engine for Geospatial Intelligence Platform

This module provides multiple methods for detecting anomalies in aircraft behavior:
- Speed anomalies (Z-score and IQR methods)
- Altitude anomalies
- Geofence violations
- Vertical rate anomalies
- ML-based anomalies (Isolation Forest)
"""

import numpy as np
from sklearn.ensemble import IsolationForest
from shapely.geometry import Point, Polygon
from typing import List, Tuple

def detect_speed_anomalies_zscore(aircraft_list,thresh_hold=2.5):
    """
    Detects speed anomalies in aircraft data using Z-score method.
    
    Parameters:
    - aircraft_list: List of aircraft objects with speed attributes
    - thresh_hold: Z-score threshold for anomaly detection (default: 2.5)
    
    Returns:
    - List of tuples containing (aircraft_id, speed, z_score) for anomalies
    """
    alerts = []

    if (len(aircraft_list) < 3):
        return alerts

    #Extract velocity
    speeds = [a["velocity"] for a in aircraft_list]
    speeds_array = np.array(speeds)

    #Mean and standard deviation
    mean = np.mean(speeds_array)
    std = np.std(speeds_array)

    if std == 0:
        return alerts
    
    # Check each aircraft
    for aircraft in aircraft_list:
        velocity = aircraft['velocity']
        z_score = abs((velocity - mean) / std)
        
        # Check anomalies
        if z_score > thresh_hold:
            velocity_kmh = velocity * 3.6
            
            if velocity < 50:  # Too slow (< 180 km/h)
                alerts.append({
                    'type': 'SPEED_ANOMALY',
                    'severity': 'MEDIUM',
                    'reason': f'Unusually slow speed: {velocity_kmh:.0f} km/h (possible stall)',
                    'icao24': aircraft['icao24'],
                    'callsign': aircraft.get('callsign', 'Unknown'),
                    'latitude': aircraft['latitude'],
                    'longitude': aircraft['longitude'],
                    'priority': 70,
                    'details': {
                        'velocity_mps': velocity,
                        'velocity_kmh': velocity_kmh,
                        'z_score': float(z_score)
                    }
                })
            elif velocity > 340:  # Too fast (> 1224 km/h)
                alerts.append({
                    'type': 'SPEED_ANOMALY',
                    'severity': 'HIGH',
                    'reason': f'Unusually fast speed: {velocity_kmh:.0f} km/h (supersonic)',
                    'icao24': aircraft['icao24'],
                    'callsign': aircraft.get('callsign', 'Unknown'),
                    'latitude': aircraft['latitude'],
                    'longitude': aircraft['longitude'],
                    'priority': 80,
                    'details': {
                        'velocity_mps': velocity,
                        'velocity_kmh': velocity_kmh,
                        'z_score': float(z_score)
                    }
                })
    
    return alerts



def detect_speed_anomalies_iqr(aircraft_list,multiplier=1.5):
    """
    Detects speed anomalies in aircraft data using IQR method.
    
    Parameters:
    - aircraft_list: List of aircraft objects with speed attributes
    - multiplier: The multiplier for the IQR (default is 1.5)
    Returns:
    - List of tuples containing (aircraft_id, speed, anomaly_type) for anomalies
    """
    alerts = []

    if (len(aircraft_list) < 5):
        return alerts

    speeds = [a["velocity"] for a in aircraft_list]
    speeds_array = np.array(speeds)

    q1 = np.percentile(speeds_array, 25)
    q3 = np.percentile(speeds_array, 75)
    iqr = q3 - q1

    lower_bound = q1 - (multiplier * iqr)
    upper_bound = q3 + (multiplier * iqr)
    for aircraft in aircraft_list:
        velocity = aircraft['velocity']
        
        if velocity < lower_bound or velocity > upper_bound:
            velocity_kmh = velocity * 3.6
            
            alerts.append({
                'type': 'SPEED_ANOMALY',
                'severity': 'MEDIUM',
                'reason': f'Speed outside normal range: {velocity_kmh:.0f} km/h',
                'icao24': aircraft['icao24'],
                'callsign': aircraft.get('callsign', 'Unknown'),
                'latitude': aircraft['latitude'],
                'longitude': aircraft['longitude'],
                'priority': 65,
                'details': {
                    'velocity_kmh': velocity_kmh,
                    'iqr_lower': lower_bound,
                    'iqr_upper': upper_bound
                }
            })
    
    return alerts

def detect_altitude_anomalies_zscore(aircraft_list,thresh_hold=2.5,max_altitude=13000):
    """
    Detects altitude anomalies in aircraft data using Z-score method.
    """
    alerts = []
    if len(aircraft_list) < 3:
        return alerts
    altitudes = [a["altitude"] for a in aircraft_list]
    altitudes_array = np.array(altitudes)
    mean = np.mean(altitudes_array)
    std = np.std(altitudes_array)
    
    if std == 0:
        return alerts
    
    for aircraft in aircraft_list:
        altitude = aircraft['altitude']
        
        if altitude > max_altitude:
            alerts.append({
                'type': 'ALTITUDE_ANOMALY',
                'severity': 'MEDIUM',
                'reason': f'Unusually high altitude: {altitude:.0f}m (above {max_altitude}m)',
                'icao24': aircraft['icao24'],
                'callsign': aircraft.get('callsign', 'Unknown'),
                'latitude': aircraft['latitude'],
                'longitude': aircraft['longitude'],
                'priority': 60,
                'details': {
                    'altitude_meters': altitude,
                    'max_allowed': max_altitude
                }
            })
    
    return alerts

def detect_geofence_violations(aircraft_list,geofences):
    """
    Check if aircraft are inside restricted zones
    
    Args:
        aircraft_list: List of aircraft dicts
        geofences: List of dicts with 'name' and 'polygon' (Shapely Polygon)
    
    Returns:
        List of alerts
    """
    alerts = []
    for aircraft in aircraft_list:
        point = Point(aircraft["longitude"], aircraft["latitude"])
        for geofence in geofences:
            if geofence["polygon"].contains(point):
                alerts.append({
                    'type': 'GEOFENCE_VIOLATION',
                    'severity': 'HIGH',
                    'reason': f'Violation of geofence: {geofence["name"]}',
                    'icao24': aircraft['icao24'],
                    'callsign': aircraft.get('callsign', 'Unknown'),
                    'latitude': aircraft['latitude'],
                    'longitude': aircraft['longitude'],
                    'priority': 90,
                    'details': {
                        'zone_name': geofence["name"]
                    }
                })
    return alerts


def detect_vertical_rate_anomalies_zscore(aircraft_list,thresh_hold=2.5,max_vrate=15):
    """
    Detects vertical rate anomalies in aircraft data using Z-score method.
    
    Parameters:
    - aircraft_list: List of aircraft objects with vertical_rate attributes
    - thresh_hold: Z-score threshold for anomaly detection (default: 2.5)
    
    Returns:
    - List of tuples containing (aircraft_id, vertical_rate, z_score) for anomalies
    """
    alerts = []
    if len(aircraft_list) < 3:
        return alerts
    vrates = [abs(a.get('vertical_rate') or 0) for a in aircraft_list]
    vrates_array = np.array(vrates)
    mean = np.mean(vrates_array)
    std = np.std(vrates_array)
    
    if std == 0:
        return alerts
    
    for aircraft in aircraft_list:

        vrate = abs(aircraft.get('vertical_rate') or 0)
        
        if vrate > max_vrate:
            alerts.append({
                'type': 'VERTICAL_RATE_ANOMALY',
                'severity': 'MEDIUM',
                'reason': f'Excessive vertical rate: {vrate:.1f} m/s',
                'icao24': aircraft['icao24'],
                'callsign': aircraft.get('callsign', 'Unknown'),
                'latitude': aircraft['latitude'],
                'longitude': aircraft['longitude'],
                'priority': 65,
                'details': {
                    'vertical_rate_mps': vrate,
                    'max_allowed': max_vrate
                }
            })
    
    return alerts

def detect_ml_based_anomalies(aircraft_list,contamination = 0.05):
    """
    Detect anomalies using Isolation Forest
    
    Args:
        aircraft_list: List of aircraft dicts
        contamination: Expected proportion of anomalies (default 5%)
    
    Returns:
        List of alerts
    """
    alerts = []
    if len(aircraft_list) < 10:
        return alerts
    
    features = []
    for a in aircraft_list:
        features.append([
            a['velocity'] if a['velocity'] is not None else 0,
            a['altitude'] if a['altitude'] is not None else 0,
            a.get('vertical_rate') or 0  
        ])
    
    features_array = np.array(features)
    if np.any(np.isnan(features_array)) or np.any(np.isinf(features_array)):
        # Skip ML detection if data quality is poor
        return alerts
    try:
        # Train Isolation Forest
        iso_forest = IsolationForest(contamination=contamination, random_state=42)
        predictions = iso_forest.fit_predict(features_array)
        
        # Get anomalies (predictions == -1)
        for i, pred in enumerate(predictions):
            if pred == -1:
                aircraft = aircraft_list[i]
                alerts.append({
                    'type': 'ML_ANOMALY',
                    'severity': 'LOW',
                    'reason': 'Unusual flight pattern detected by ML model',
                    'icao24': aircraft['icao24'],
                    'callsign': aircraft.get('callsign', 'Unknown'),
                    'latitude': aircraft['latitude'],
                    'longitude': aircraft['longitude'],
                    'priority': 50,
                    'details': {
                        'velocity': aircraft['velocity'],
                        'altitude': aircraft['altitude'],
                        'model': 'IsolationForest'
                    }
                })
    except Exception as e:
        # If ML detection fails, just skip it (don't crash the whole system)
        print(f"Warning: ML-based anomaly detection failed: {e}")
        return []
    
    return alerts

class AnomalyDetector:
    """
    Main anomaly detection coordinator
    Runs all detection methods and aggregates results
    """
    
    def __init__(self):
        """Initialize detector with default geofences"""
        self.geofences = [
            {
                'name': 'Military Base Alpha',
                'polygon': Polygon([
                    (11.5, 48.0),
                    (12.0, 48.0),
                    (12.0, 48.5),
                    (11.5, 48.5),
                    (11.5, 48.0)
                ])
            },
            {
                'name': 'Nuclear Facility Beta',
                'polygon': Polygon([
                    (2.0, 51.0),
                    (2.5, 51.0),
                    (2.5, 51.5),
                    (2.0, 51.5),
                    (2.0, 51.0)
                ])
            }
        ]
    
    def detect_all(self, aircraft_list):
        """
        Run all anomaly detection methods
        
        Args:
            aircraft_list: List of dicts with keys:
                - icao24, callsign, latitude, longitude
                - altitude, velocity, vertical_rate, heading
        
        Returns:
            List of alert dicts
        """
        all_alerts = []
        
        if not aircraft_list:
            return all_alerts
        
        # 1. Speed anomalies (Z-score)
        speed_alerts = detect_speed_anomalies_zscore(aircraft_list)
        all_alerts.extend(speed_alerts)
        
        # 2. Altitude anomalies
        altitude_alerts = detect_altitude_anomalies_zscore(aircraft_list)
        all_alerts.extend(altitude_alerts)
        
        # 3. Geofence violations
        geofence_alerts = detect_geofence_violations(aircraft_list, self.geofences)
        all_alerts.extend(geofence_alerts)
        
        # 4. Vertical rate anomalies
        vrate_alerts = detect_vertical_rate_anomalies_zscore(aircraft_list)
        all_alerts.extend(vrate_alerts)
        
        # 5. ML-based anomalies (if enough data)
        if len(aircraft_list) >= 10:
            ml_alerts = detect_ml_based_anomalies(aircraft_list)
            all_alerts.extend(ml_alerts)
        
        # Deduplicate
        unique_alerts = self._deduplicate_alerts(all_alerts)
        
        return unique_alerts
    
    def _deduplicate_alerts(self, alerts):
        """Remove duplicate alerts, keep highest severity"""
        seen = {}
        
        for alert in alerts:
            key = (alert['icao24'], alert['type'])
            
            if key not in seen:
                seen[key] = alert
            else:
                # Keep higher severity
                severity_order = {'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}
                current = severity_order.get(seen[key]['severity'], 0)
                new = severity_order.get(alert['severity'], 0)
                
                if new > current:
                    seen[key] = alert
        
        return list(seen.values())
    
    def add_geofence(self, name, polygon_coords):
        """Add new geofence"""
        self.geofences.append({
            'name': name,
            'polygon': Polygon(polygon_coords)
        })
    
    def remove_geofence(self, name):
        """Remove geofence by name"""
        self.geofences = [g for g in self.geofences if g['name'] != name]


# ============= TEST CODE =============

if __name__ == "__main__":
    print("="*60)
    print("ANOMALY DETECTION ENGINE TEST")
    print("="*60)
    
    # Test data
    test_aircraft = [
        {
            'icao24': 'TEST001',
            'callsign': 'ABC123',
            'latitude': 48.1,
            'longitude': 11.6,
            'altitude': 5000,
            'velocity': 45,  # Too slow
            'vertical_rate': 5,
            'heading': 90
        },
        {
            'icao24': 'TEST002',
            'callsign': 'DEF456',
            'latitude': 48.2,
            'longitude': 11.7,
            'altitude': 8000,
            'velocity': 200,
            'vertical_rate': 3,
            'heading': 180
        },
        {
            'icao24': 'TEST003',
            'callsign': 'GHI789',
            'latitude': 51.2,
            'longitude': 2.2,
            'altitude': 9000,
            'velocity': 220,
            'vertical_rate': 2,
            'heading': 270
        }
    ]
    
    # Run detection
    detector = AnomalyDetector()
    alerts = detector.detect_all(test_aircraft)
    
    print(f"\nAnalyzed: {len(test_aircraft)} aircraft")
    print(f"Detected: {len(alerts)} alerts")
    print("="*60)
    
    for i, alert in enumerate(alerts, 1):
        print(f"\n{i}. [{alert['severity']}] {alert['type']}")
        print(f"   Aircraft: {alert['callsign']} ({alert['icao24']})")
        print(f"   Reason: {alert['reason']}")
        print(f"   Location: ({alert['latitude']:.2f}, {alert['longitude']:.2f})")
    
    print("\n" + "="*60)
    print("Test complete!")

