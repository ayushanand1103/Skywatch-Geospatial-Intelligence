"""Manual OpenSky connectivity check; does not write to the database."""

import json
import requests


def test_opensky_api():
    """Fetch current anonymous state vectors once; API rate limits apply."""
    print('Testing OpenSky Network API...')
    try:
        response = requests.get('https://opensky-network.org/api/states/all', timeout=30)
        if response.status_code == 429:
            print('OpenSky rate limit reached. Try again later.')
            return False
        response.raise_for_status()
        data = response.json()
        states = data.get('states') or []
        if not isinstance(states, list):
            raise ValueError('Unexpected states response: expected a list')
        print(f'Total aircraft tracked: {len(states)}')
        valid_aircraft = [
            state for state in states
            if isinstance(state, list) and len(state) >= 12
            and state[5] is not None and state[6] is not None
        ]
        print(f'Aircraft with valid positions: {len(valid_aircraft)}')
        if valid_aircraft:
            sample = valid_aircraft[0]
            print('\nSample aircraft:')
            print(f'  ICAO24: {sample[0]}')
            print(f"  Callsign: {sample[1].strip() if sample[1] else 'Unknown'}")
            print(f'  Origin: {sample[2]}')
            print(f'  Longitude: {sample[5]}')
            print(f'  Latitude: {sample[6]}')
            print(f'  Altitude: {sample[7]} meters')
            print(f'  Velocity: {sample[9]} m/s')
            print(f'  Heading: {sample[10]} degrees')
            print('\nRaw state vector:')
            print(json.dumps(sample, indent=2))
        return True
    except (requests.exceptions.RequestException, ValueError, TypeError) as exc:
        print(f'Error fetching data: {exc}')
        return False


if __name__ == '__main__':
    raise SystemExit(0 if test_opensky_api() else 1)
