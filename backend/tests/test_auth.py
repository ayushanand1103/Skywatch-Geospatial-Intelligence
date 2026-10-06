"""Run with python -m unittest discover -s tests."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import get_db
from app.models import User
from app.auth import SECRET_KEY


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        User.__table__.create(self.engine)
        def session():
            with Session(self.engine) as db:
                yield db
        app.dependency_overrides[get_db] = session
        self.client = TestClient(app)
        self.credentials = {'username': 'tester', 'password': 'A-long-test-password-123'}

    def tearDown(self):
        app.dependency_overrides.clear()
        self.client.close()
        self.engine.dispose()

    def test_registration_login_and_protection(self):
        response = self.client.post('/api/auth/register', json=self.credentials)
        self.assertEqual(response.status_code, 201)
        self.assertNotIn('password_hash', response.json())
        self.assertEqual(self.client.post('/api/auth/register', json=self.credentials).status_code, 409)
        with Session(self.engine) as db:
            user = db.query(User).first()
            self.assertNotEqual(user.password_hash, self.credentials['password'])
            self.assertTrue(user.password_hash.startswith('$argon2'))
        token = self.client.post('/api/auth/login', data=self.credentials).json()['access_token']
        headers = {'Authorization': 'Bearer ' + token}
        self.assertEqual(self.client.get('/api/auth/me', headers=headers).json()['username'], 'tester')
        for path in ['/api/scheduler/trigger', '/api/aircraft/fetch-and-store', '/api/alerts/detect', '/api/alerts/1/resolve', '/api/alerts/1/acknowledge']:
            self.assertEqual(self.client.post(path).status_code, 401)
        self.assertEqual(self.client.post('/api/scheduler/trigger', headers=headers).status_code, 403)
        with Session(self.engine) as db:
            user = db.query(User).first(); user.role = 'admin'; db.commit()
        with patch('app.main.trigger_job_now', return_value=True):
            self.assertEqual(self.client.post('/api/scheduler/trigger', headers=headers).status_code, 200)
        self.assertEqual(self.client.post('/api/auth/login', data={**self.credentials, 'password': 'wrong'}).status_code, 401)
        self.assertEqual(self.client.post('/api/auth/login', data={**self.credentials, 'username': 'missing'}).status_code, 401)
        self.assertEqual(self.client.get('/api/auth/me', headers={'Authorization': 'Bearer invalid'}).status_code, 401)
        claims = jwt.decode(token, SECRET_KEY, algorithms=['HS256'], audience='skywatch-api')
        claims['exp'] = datetime.now(timezone.utc) - timedelta(minutes=1)
        expired = jwt.encode(claims, SECRET_KEY, algorithm='HS256')
        self.assertEqual(self.client.get('/api/auth/me', headers={'Authorization': 'Bearer '+expired}).status_code, 401)
        with Session(self.engine) as db:
            user = db.query(User).first(); user.is_active = False; db.commit()
        self.assertEqual(self.client.get('/api/auth/me', headers=headers).status_code, 401)

    def test_roles(self):
        self.client.post('/api/auth/register', json={**self.credentials, 'role': 'admin'})
        token = self.client.post('/api/auth/login', data=self.credentials).json()['access_token']
        headers = {'Authorization': 'Bearer '+token}
        self.assertEqual(self.client.get('/api/auth/me', headers=headers).json()['role'], 'viewer')
        for role in ['viewer', 'analyst', 'admin']:
            with Session(self.engine) as db:
                user = db.query(User).first(); user.role = role; db.commit()
            self.assertEqual(self.client.get('/api/scheduler/status', headers=headers).status_code, 200)
            expected = 403 if role == 'viewer' else 404
            with patch('app.main.crud.resolve_alert', return_value=None):
                self.assertEqual(self.client.post('/api/alerts/999/resolve', headers=headers).status_code, expected)
            with patch('app.main.trigger_job_now', return_value=True):
                self.assertEqual(self.client.post('/api/scheduler/trigger', headers=headers).status_code, 200 if role == 'admin' else 403)
        self.assertEqual(self.client.get('/api/aircraft').status_code, 401)

    def test_input_validation(self):
        self.assertEqual(self.client.post('/api/auth/register', json={'username':'bad name','password':'long-enough-password'}).status_code, 422)
        self.assertEqual(self.client.post('/api/auth/register', json={'username':'tester','password':'short'}).status_code, 422)


if __name__ == '__main__':
    unittest.main()
