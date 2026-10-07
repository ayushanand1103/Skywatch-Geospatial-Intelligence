"""Custom polygon validation, persistence and permission checks."""
import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.main import app
from app.database import get_db
from app.models import User, Geofence

class GeofenceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        User.__table__.create(self.engine)
        Geofence.__table__.create(self.engine)
        def sessions():
            with Session(self.engine) as db:
                yield db
        app.dependency_overrides[get_db] = sessions
        self.client = TestClient(app)
        credentials = {'username': 'zone_tester', 'password': 'Testing-zone-password-123'}
        self.client.post('/api/auth/register', json=credentials)
        token = self.client.post('/api/auth/login', data=credentials).json()['access_token']
        self.headers = {'Authorization': 'Bearer ' + token}
        self.payload = {'name': 'Test zone', 'coordinates': [[77,28],[78,28],[78,29],[77,29]]}
    def tearDown(self):
        app.dependency_overrides.clear()
        self.client.close()
        self.engine.dispose()
    def make_analyst(self):
        with Session(self.engine) as db:
            db.query(User).first().role = 'analyst'
            db.commit()
    def test_permissions_and_persistence(self):
        self.assertEqual(self.client.post('/api/geofences', json=self.payload).status_code, 401)
        self.assertEqual(self.client.post('/api/geofences', json=self.payload, headers=self.headers).status_code, 403)
        self.make_analyst()
        response = self.client.post('/api/geofences', json=self.payload, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        zone_id = response.json()['properties']['id']
        listed = self.client.get('/api/geofences', headers=self.headers).json()['features']
        self.assertTrue(any(f['properties']['name']=='Test zone' for f in listed))
        self.assertEqual(self.client.post(f'/api/geofences/{zone_id}/deactivate', headers=self.headers).status_code, 200)
        listed = self.client.get('/api/geofences', headers=self.headers).json()['features']
        self.assertFalse(any(f['properties']['id']==zone_id for f in listed))
        with Session(self.engine) as db:
            self.assertFalse(db.get(Geofence, zone_id).is_active)
    def test_rejects_invalid_polygons(self):
        self.make_analyst()
        for coordinates in [[[77,28],[78,29],[77,29],[78,28]],[[181,28],[78,28],[78,29]],[[1,1],[2,2],[3,3]]]:
            result=self.client.post('/api/geofences',json={**self.payload,'coordinates':coordinates},headers=self.headers)
            self.assertEqual(result.status_code,400)
        self.assertEqual(self.client.post('/api/geofences',json={**self.payload,'name':'   '},headers=self.headers).status_code,400)

if __name__ == '__main__': unittest.main()
