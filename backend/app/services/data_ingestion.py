"""
Data Ingestion Pipeline - Fetches data from external APIs and stores in database
Runs scheduled jobs in background
"""

import os
import requests
import time
from datetime import datetime, timezone  
from typing import Optional, Dict, List
from sqlalchemy.orm import Session
import logging

from ..database import SessionLocal
from .. import CRUD as crud

logger = logging.getLogger(__name__)

# ============= OPENSKY NETWORK =============

class OpenSkyFetcher:
    """Fetches aircraft data from OpenSky Network"""
    
    BASE_URL = "https://opensky-network.org/api/states/all"
    
    def __init__(self, client_id: Optional[str] = None, client_secret: Optional[str] = None):
        """Use anonymous access or optional OpenSky OAuth2 client credentials."""
        self.client_id = client_id or os.getenv('OPENSKY_CLIENT_ID')
        self.client_secret = client_secret or os.getenv('OPENSKY_CLIENT_SECRET')
        if bool(self.client_id) != bool(self.client_secret):
            raise ValueError('Both OPENSKY_CLIENT_ID and OPENSKY_CLIENT_SECRET are required')
        self.token = None
        self.token_expiry = 0
        self.last_fetch_time = None
        self.fetch_count = 0

    def _headers(self):
        if not self.client_id:
            return {}
        if not self.token or time.monotonic() >= self.token_expiry:
            response = requests.post(
                'https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token',
                data={'grant_type': 'client_credentials', 'client_id': self.client_id,
                      'client_secret': self.client_secret}, timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
            self.token = payload['access_token']
            self.token_expiry = time.monotonic() + max(0, payload.get('expires_in', 1800) - 60)
        return {'Authorization': f'Bearer {self.token}'}

    def fetch_aircraft_data(self, max_retries: int = 3) -> Optional[Dict]:
        """
        Fetch current aircraft states from OpenSky with retry logic
        Returns raw API response or None if error
        """
        for attempt in range(max_retries):
            try:
                logger.info(f"Fetching aircraft data from OpenSky Network... (attempt {attempt + 1}/{max_retries})")
                
                response = requests.get(
                    self.BASE_URL,
                    headers=self._headers(),
                    timeout=45  
                )
                if response.status_code == 401:
                    self.token = None
                if response.status_code == 429:
                    logger.warning('OpenSky rate limit reached; skipping this run')
                    return None
                response.raise_for_status()
                
                data = response.json()
                self.last_fetch_time = datetime.now(timezone.utc)
                self.fetch_count += 1
                
                total_states = len(data.get('states') or [])
                logger.info(f" Fetched {total_states} aircraft states")
                
                return data
                
            except requests.exceptions.Timeout:
                logger.warning(f"  OpenSky API timeout (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    wait_time = 5 * (attempt + 1)  # Exponential backoff: 5s, 10s, 15s
                    logger.info(f"Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(" All retry attempts exhausted - OpenSky API timeout")
                    return None
                    
            except requests.exceptions.RequestException as e:
                logger.error(f" OpenSky API error: {e}")
                if attempt < max_retries - 1:
                    logger.info("Retrying after 5s...")
                    time.sleep(5)
                    continue
                return None
                
            except Exception as e:
                logger.error(f" Unexpected error fetching data: {e}")
                return None
        
        return None
    
    def parse_aircraft_state(self, state: List) -> Optional[Dict]:
        """
        Parse OpenSky state vector into our format
        state format: [icao24, callsign, origin_country, time_position, 
                       last_contact, longitude, latitude, baro_altitude, 
                       on_ground, velocity, true_track, vertical_rate, ...]
        """
        try:
            # Skip if no position data
            if state[5] is None or state[6] is None:
                return None
            
            return {
                'icao24': state[0],
                'callsign': state[1].strip() if state[1] else None,
                'origin_country': state[2],
                'longitude': float(state[5]),
                'latitude': float(state[6]),
                'altitude': float(state[7]) if state[7] is not None else None,
                'velocity': float(state[9]) if state[9] is not None else None,
                'heading': float(state[10]) if state[10] is not None else None,
                'vertical_rate': float(state[11]) if state[11] is not None else None,
                'on_ground': bool(state[8]) if state[8] is not None else False,
                'last_update': datetime.fromtimestamp(state[4], timezone.utc) if state[4] is not None else datetime.now(timezone.utc),  
                'timestamp': datetime.fromtimestamp(state[3], timezone.utc) if state[3] is not None else datetime.now(timezone.utc)     
            }
        except (IndexError, ValueError, TypeError) as e:
            logger.warning(f"Failed to parse state {state!r}: {e}")
            return None
    
    def store_aircraft_data(self, data: Dict, db: Session) -> Dict:
        """
        Store aircraft data in database
        Returns statistics about what was stored
        """
        states = data.get('states') or []
        
        stored_aircraft = 0
        stored_positions = 0
        skipped = 0
        errors = 0
        
        for state in states:
            try:
                parsed = self.parse_aircraft_state(state)
                
                if parsed is None:
                    skipped += 1
                    continue
                
                # Update or create aircraft
                aircraft = crud.get_or_create_aircraft(
                    db, 
                    parsed['icao24'], 
                    parsed
                )
                stored_aircraft += 1
                
                # Store position history
                crud.create_aircraft_position(
                    db,
                    aircraft.id,
                    parsed
                )
                stored_positions += 1
                
            except Exception as e:
                logger.error(f"Error storing aircraft {state!r}: {e}")
                db.rollback()
                errors += 1
                continue
        
        stats = {
            'fetched': len(states),
            'stored_aircraft': stored_aircraft,
            'stored_positions': stored_positions,
            'skipped': skipped,
            'errors': errors,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        logger.info(
            f" Storage stats: {stored_aircraft} aircraft, "
            f"{stored_positions} positions, {skipped} skipped, {errors} errors"
        )
        
        return stats

# ============= SCHEDULED JOB =============

def fetch_and_store_aircraft_job():
    """
    Job function that runs on schedule
    Fetches aircraft data and stores in database
    """
    logger.info("=" * 60)
    logger.info(" Starting scheduled aircraft fetch job")
    logger.info("=" * 60)
    
    db = SessionLocal()
    
    try:
        fetcher = OpenSkyFetcher()
        # Fetch data
        data = fetcher.fetch_aircraft_data()
        
        if data is None:
            logger.warning("  No data fetched, skipping storage")
            return
        
        # Store in database
        stats = fetcher.store_aircraft_data(data, db)
        
        # Get overall stats
        db_stats = crud.get_stats(db)
        
        logger.info("=" * 60)
        logger.info(" Job completed successfully")
        logger.info(f" Total in database: {db_stats['total_aircraft']} aircraft, "
                   f"{db_stats['total_aircraft_positions']} positions")
        logger.info("=" * 60)
        
        return stats
        
    except Exception as e:
        logger.error(f" Job failed with error: {e}")
        import traceback
        traceback.print_exc()
        return None
        
    finally:
        db.close()

# ============= TEST FUNCTION =============

def test_ingestion():
    """Test function - run manually to verify ingestion works"""
    logger.info("Testing data ingestion pipeline...")
    result = fetch_and_store_aircraft_job()
    
    if result:
        logger.info(" Test successful!")
        logger.info(f"Stats: {result}")
    else:
        logger.error(" Test failed")

if __name__ == "__main__":
    # Run test when script is executed directly
    test_ingestion()