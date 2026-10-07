"""FastAPI endpoints and background task lifecycle."""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
import os

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from geoalchemy2.shape import to_shape
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .database import get_db, SessionLocal
from . import CRUD as crud
from . import Spatial_queries as spatial
from .models import Alert
from .auth import router as auth_router, get_current_user, require_roles
from .services.data_ingestion import OpenSkyFetcher
from .services.scheduler import start_scheduler, stop_scheduler, get_scheduler_status, trigger_job_now

logger = logging.getLogger(__name__)


def run_periodic_anomaly_detection():
    with SessionLocal() as db:
        try:
            crud.run_anomaly_detection_on_all_aircraft(db)
            crud.auto_resolve_old_alerts(db)
        except Exception:
            db.rollback()
            logger.exception('Periodic anomaly detection failed')


@asynccontextmanager
async def lifespan(app):
    # Fail startup if the configured database cannot be reached.
    def check_database():
        with SessionLocal() as db:
            db.execute(text('SELECT 1'))
    await run_in_threadpool(check_database)
    enabled = os.getenv('SCHEDULER_ENABLED', 'true').lower() in {'true', '1', 'yes'}
    try:
        if enabled:
            # Global anonymous requests cost 4 credits each; 20 minutes leaves margin.
            instance = start_scheduler(float(os.getenv('FETCH_INTERVAL_MINUTES', '20')))
            instance.add_job(run_periodic_anomaly_detection, 'interval', minutes=5,
                             id='anomaly_detection', max_instances=1, coalesce=True,
                             replace_existing=True)
        yield
    finally:
        if enabled:
            await run_in_threadpool(stop_scheduler)


app = FastAPI(title='Geospatial Intelligence Platform API', version='0.2.0', lifespan=lifespan)
app.include_router(auth_router)
app.add_middleware(CORSMiddleware,
    allow_origins=os.getenv('CORS_ORIGINS', 'http://localhost:5173,http://localhost:3000').split(','),
    allow_credentials=True, allow_methods=['GET', 'POST'], allow_headers=['*'])


def now():
    return datetime.now(timezone.utc).isoformat()


def collection(features):
    return {'type': 'FeatureCollection', 'features': features, 'count': len(features), 'timestamp': now()}


def viewport(db, min_lon, min_lat, max_lon, max_lat, limit):
    try:
        return spatial.get_aircraft_in_viewport(db, min_lon=min_lon, min_lat=min_lat,
                                               max_lon=max_lon, max_lat=max_lat, limit=limit)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def fetch_data():
    fetcher = OpenSkyFetcher()
    data = fetcher.fetch_aircraft_data(max_retries=1)
    if data is None:
        raise HTTPException(503, 'OpenSky data unavailable or rate limited')
    return fetcher, data


@app.get('/')
def root():
    return {'status': 'operational', 'service': app.title, 'version': app.version, 'timestamp': now()}


@app.get('/api/scheduler/status', dependencies=[Depends(get_current_user)])
def scheduler_status():
    return get_scheduler_status()


@app.post('/api/scheduler/trigger', dependencies=[Depends(require_roles('admin'))])
def trigger_fetch_now():
    if not trigger_job_now():
        raise HTTPException(503, 'Scheduler not running')
    return {'status': 'triggered', 'message': 'Data fetch scheduled immediately'}


@app.get('/api/aircraft/live', dependencies=[Depends(get_current_user)])
def aircraft_live(limit: int = Query(100, ge=0, le=10000)):
    fetcher, data = fetch_data()
    states = data.get('states') or []
    aircraft = []
    for state in states:
        if len(aircraft) >= limit:
            break
        parsed = fetcher.parse_aircraft_state(state)
        if parsed is not None:
            aircraft.append(parsed)
    return {'count': len(aircraft), 'total_tracked': len(states), 'aircraft': aircraft, 'timestamp': now()}


@app.post('/api/aircraft/fetch-and-store', dependencies=[Depends(require_roles('admin'))])
def fetch_and_store(limit: int = Query(100, ge=1, le=10000), db: Session = Depends(get_db)):
    fetcher, data = fetch_data()
    states = data.get('states') or []
    stats = fetcher.store_aircraft_data({'states': states[:limit]}, db)
    return {'status': 'success' if not stats['errors'] else 'partial', 'fetched': len(states),
            'stored': stats['stored_positions'], 'stats': stats}


@app.get('/api/aircraft', dependencies=[Depends(get_current_user)])
def aircraft_list(bbox: str = None, limit: int = Query(1000, ge=0, le=10000), db: Session = Depends(get_db)):
    bounds = [-180, -90, 180, 90]
    if bbox is not None:
        try:
            bounds = [float(x) for x in bbox.split(',')]
            if len(bounds) != 4:
                raise ValueError()
        except ValueError as exc:
            raise HTTPException(400, 'bbox must be min_lon,min_lat,max_lon,max_lat') from exc
    return collection(viewport(db, *bounds, limit))


@app.get('/api/aircraft/viewport', dependencies=[Depends(get_current_user)])
def aircraft_viewport(min_lon: float, min_lat: float, max_lon: float, max_lat: float,
                      limit: int = Query(1000, ge=0, le=10000), db: Session = Depends(get_db)):
    return collection(viewport(db, min_lon, min_lat, max_lon, max_lat, limit))


@app.get('/api/aircraft/near', dependencies=[Depends(get_current_user)])
def aircraft_near(lon: float = Query(..., ge=-180, le=180), lat: float = Query(..., ge=-90, le=90),
                  radius_km: float = Query(50, ge=0, le=20040), limit: int = Query(100, ge=0, le=10000),
                  db: Session = Depends(get_db)):
    aircraft = spatial.get_aircraft_near_point(db, lon, lat, radius_km, limit)
    return {'center': {'lon': lon, 'lat': lat}, 'radius_km': radius_km,
            'aircraft': aircraft, 'count': len(aircraft), 'timestamp': now()}


@app.get('/api/aircraft/resolve/{callsign}', dependencies=[Depends(get_current_user)])
def resolve_callsign(callsign: str, db: Session = Depends(get_db)):
    from sqlalchemy import func
    from .models import Aircraft
    matches = db.query(Aircraft).filter(
        func.upper(func.trim(Aircraft.call_sign)) == callsign.strip().upper()
    ).all()
    if not matches:
        raise HTTPException(404, 'Callsign not found. Enter the aircraft ICAO24 code instead.')
    if len(matches) > 1:
        raise HTTPException(409, 'Multiple aircraft have this callsign. Enter the unique ICAO24 code instead.')
    return {'icao24': matches[0].icao24, 'callsign': matches[0].call_sign}


@app.get('/api/aircraft/{icao24}/sessions', dependencies=[Depends(get_current_user)])
def flight_sessions(icao24: str, hours: int = Query(720, ge=1, le=720), db: Session = Depends(get_db)):
    from datetime import timedelta
    from .flight_sessions import aircraft_sessions
    aircraft = crud.get_aircraft_by_icao24(db, icao24.lower())
    if aircraft is None:
        raise HTTPException(404, 'Aircraft not found')
    groups = aircraft_sessions(db, aircraft.id, datetime.now(timezone.utc) - timedelta(hours=hours))
    return {'sessions': [
        {'id': group[0].id, 'icao24': aircraft.icao24,
         'start_time': group[0].created_at.isoformat(), 'end_time': group[-1].created_at.isoformat(),
         'point_count': len(group),
         'has_trajectory': len({tuple(to_shape(p.position).coords[0]) for p in group}) >= 2,
         'basis': 'Observed takeoff or tracking gap over two hours; older observations have no ground status'}
        for group in reversed(groups)]}


@app.get('/api/aircraft/{icao24}/trajectory', dependencies=[Depends(get_current_user)])
def trajectory(icao24: str, hours: int = Query(1, ge=1, le=720), session_id: int = Query(None, ge=1), db: Session = Depends(get_db)):
    if crud.get_aircraft_by_icao24(db, icao24) is None:
        raise HTTPException(404, 'Aircraft not found')
    result = spatial.get_aircraft_trajectory(db, icao24, hours, session_id)
    if result is None:
        return {'type': 'Feature', 'geometry': None, 'properties': {'icao24': icao24, 'count': 0}}
    result['properties']['count'] = result['properties']['point_count']
    return result


@app.get('/api/heatmap/density', dependencies=[Depends(get_current_user)])
def density(resolution: int = Query(7, ge=0, le=15), min_count: int = Query(5, ge=1), db: Session = Depends(get_db)):
    cells = spatial.get_density_heatmap(db, resolution, min_count)
    return {'h3_resolution': resolution, 'cells': cells, 'count': len(cells), 'timestamp': now()}


@app.get('/api/stats/spatial', dependencies=[Depends(get_current_user)])
def spatial_stats(db: Session = Depends(get_db)):
    return spatial.get_spatial_stats(db)


@app.get('/api/analytics/routes', dependencies=[Depends(get_current_user)])
def routes(limit: int = Query(20, ge=0, le=1000), db: Session = Depends(get_db)):
    rows = spatial.get_busiest_routes(db, limit)
    return {'routes': rows, 'count': len(rows), 'timestamp': now()}


def serialize_alert(alert):
    point = to_shape(alert.position)
    return {'id': alert.id, 'type': alert.alert_type, 'severity': alert.severity,
            'reason': alert.reason, 'aircraft_icao24': alert.aircraft_icao24,
            'aircraft_callsign': alert.aircraft_callsign, 'latitude': point.y, 'longitude': point.x,
            'detected_at': alert.detected_at.isoformat(), 'resolved_at': alert.resolved_at.isoformat() if alert.resolved_at else None,
            'is_active': alert.is_active, 'is_acknowledged': alert.is_acknowledged,
            'priority': alert.priority, 'details': alert.details or {}}


@app.get('/api/alerts', dependencies=[Depends(get_current_user)])
def alerts(severity: str = None, active_only: bool = True, limit: int = Query(100, ge=0, le=1000), db: Session = Depends(get_db)):
    query = db.query(Alert)
    if active_only:
        query = query.filter(Alert.is_active.is_(True))
    if severity:
        query = query.filter(Alert.severity == severity.upper())
    rows = query.order_by(Alert.priority.desc(), Alert.detected_at.desc()).limit(limit).all()
    result = [serialize_alert(a) for a in rows]
    return {'alerts': result, 'count': len(result)}


@app.get('/api/alerts/aircraft/{icao24}', dependencies=[Depends(get_current_user)])
def aircraft_alerts(icao24: str, db: Session = Depends(get_db)):
    return {'alerts': [serialize_alert(a) for a in crud.get_alerts_for_aircraft(db, icao24)]}


@app.post('/api/alerts/{alert_id}/acknowledge', dependencies=[Depends(require_roles('analyst', 'admin'))])
def acknowledge(alert_id: int, db: Session = Depends(get_db)):
    if crud.acknowledge_alert(db, alert_id) is None:
        raise HTTPException(404, 'Alert not found')
    return {'status': 'acknowledged'}


@app.post('/api/alerts/{alert_id}/resolve', dependencies=[Depends(require_roles('analyst', 'admin'))])
def resolve(alert_id: int, db: Session = Depends(get_db)):
    if crud.resolve_alert(db, alert_id) is None:
        raise HTTPException(404, 'Alert not found')
    return {'status': 'resolved'}


@app.get('/api/alerts/hotspots', dependencies=[Depends(get_current_user)])
def anomaly_hotspots(db: Session = Depends(get_db)):
    """Active alert counts grouped into one-degree geographic cells."""
    rows = db.execute(text("""
        SELECT floor(ST_X(position::geometry)) AS cell_lon,
               floor(ST_Y(position::geometry)) AS cell_lat,
               count(*) AS alert_count,
               count(DISTINCT aircraft_icao24) AS aircraft_count,
               jsonb_agg(jsonb_build_object(
                   'id', id, 'icao24', aircraft_icao24,
                   'callsign', aircraft_callsign, 'type', alert_type,
                   'severity', severity, 'reason', reason,
                   'detected_at', detected_at
               ) ORDER BY detected_at DESC, id DESC) AS alerts,
               avg(ST_X(position::geometry)) AS longitude,
               avg(ST_Y(position::geometry)) AS latitude
        FROM alerts WHERE is_active AND position IS NOT NULL
        GROUP BY cell_lon, cell_lat ORDER BY alert_count DESC
    """)).mappings().all()
    return {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [r['longitude'], r['latitude']]},
         'properties': {'count': r['alert_count'], 'aircraft_count': r['aircraft_count'], 'alerts': r['alerts']}}
        for r in rows], 'total_active_alerts': sum(r['alert_count'] for r in rows)}


@app.get('/api/alerts/stats', dependencies=[Depends(get_current_user)])
def alert_stats(db: Session = Depends(get_db)):
    return crud.get_alert_statistics(db)


@app.post('/api/alerts/detect', dependencies=[Depends(require_roles('analyst', 'admin'))])
def detect(db: Session = Depends(get_db)):
    return {'alerts_created': len(crud.run_anomaly_detection_on_all_aircraft(db))}




# Custom fences are persisted; detector defaults remain visible as built-in zones.
from pydantic import BaseModel, Field
from shapely.geometry import Polygon, mapping
from .models import Geofence, Aircraft

class GeofenceInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    coordinates: list[list[float]] = Field(min_length=3, max_length=500)

def fence_feature(fence_id, name, coordinates, builtin=False):
    return {'type': 'Feature', 'geometry': mapping(Polygon(coordinates)),
            'properties': {'id': fence_id, 'name': name, 'builtin': builtin}}

@app.get('/api/geofences', dependencies=[Depends(get_current_user)])
def geofences(db: Session = Depends(get_db)):
    from .services.anomaly_detection import AnomalyDetector
    features = [fence_feature(f'builtin-{i}', f['name'], list(f['polygon'].exterior.coords), True)
                for i, f in enumerate(AnomalyDetector().geofences)]
    features.extend(fence_feature(f.id, f.name, f.coordinates)
                    for f in db.query(Geofence).filter(Geofence.is_active.is_(True)).order_by(Geofence.id).all())
    return collection(features)

@app.post('/api/geofences', dependencies=[Depends(require_roles('analyst', 'admin'))])
def create_geofence(payload: GeofenceInput, db: Session = Depends(get_db)):
    if not payload.name.strip() or any(len(c) != 2 or not (-180 <= c[0] <= 180 and -90 <= c[1] <= 90) for c in payload.coordinates):
        raise HTTPException(400, 'Provide a name and valid longitude, latitude pairs.')
    polygon = Polygon(payload.coordinates)
    if not polygon.is_valid or polygon.is_empty or polygon.area == 0:
        raise HTTPException(400, 'The polygon must enclose an area without crossing its own edges.')
    fence = Geofence(name=payload.name.strip(), coordinates=payload.coordinates)
    db.add(fence); db.commit(); db.refresh(fence)
    return fence_feature(fence.id, fence.name, fence.coordinates)

@app.post('/api/geofences/{fence_id}/deactivate', dependencies=[Depends(require_roles('analyst', 'admin'))])
def deactivate_geofence(fence_id: int, db: Session = Depends(get_db)):
    fence = db.get(Geofence, fence_id)
    if fence is None:
        raise HTTPException(404, 'Geofence not found')
    fence.is_active = False; db.commit()
    return {'status': 'deactivated'}

@app.get('/api/geofences/{fence_id}/aircraft', dependencies=[Depends(get_current_user)])
def geofence_aircraft(fence_id: str, limit: int = Query(1000, ge=1, le=10000), db: Session = Depends(get_db)):
    from datetime import timedelta
    from sqlalchemy import cast, func
    from geoalchemy2 import Geometry
    fences = geofences(db)['features']
    feature = next((f for f in fences if str(f['properties']['id']) == fence_id), None)
    if feature is None:
        raise HTTPException(404, 'Active geofence not found')
    polygon = Polygon(feature['geometry']['coordinates'][0])
    rows = db.query(Aircraft).filter(
        Aircraft.last_update >= datetime.now(timezone.utc) - timedelta(minutes=30),
        func.ST_Intersects(cast(Aircraft.last_position, Geometry('POINT', srid=4326)), func.ST_GeomFromText(polygon.wkt, 4326)),
    ).order_by(Aircraft.id).limit(limit).all()
    features = []
    for a in rows:
        point = to_shape(a.last_position)
        features.append({'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [point.x, point.y]},
                         'properties': {'icao24': a.icao24, 'callsign': a.call_sign, 'origin_country': a.origin_country,
                                        'altitude': a.altitude_meters, 'velocity': a.velocity_mps, 'heading': a.heading_,
                                        'last_update': a.last_update.isoformat()}})
    return collection(features)


if __name__ == '__main__':
    import uvicorn
    uvicorn.run('app.main:app', host='127.0.0.1', port=8000, reload=True)
