"""Create the custom geofence table without changing existing data."""
from app.database import engine
from app.models import Geofence
Geofence.__table__.create(engine, checkfirst=True)
print('Custom geofence table ready.')
