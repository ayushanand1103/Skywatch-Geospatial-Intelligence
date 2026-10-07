# Skywatch frontend

React 18 + TypeScript, MapLibre, Axios, Zustand, and custom dark UI.

Run `npm install`, then `npm run dev`. Open http://127.0.0.1:5173.
The Vite development proxy forwards `/api` to http://127.0.0.1:8000.
Start the backend first. Register or sign in with an existing account.
Viewer, analyst, and admin controls follow the backend role.

Tokens are held in sessionStorage and removed on sign-out or unauthorized responses.
The map uses OpenStreetMap raster tiles with attribution; internet is needed for tiles.
The density toggle visualizes the displayed aircraft, not stored H3 sample history.
No fabricated telemetry is shown. Empty states reflect the backend data.
For production, serve the frontend and `/api` through a same-origin reverse proxy.


Spatial workspaces:
- Spatial Explorer: radius search and automatic queries for the visible map viewport. Both use aircraft observed in the last 30 minutes and expose result limits.
- Density: backend H3 polygons and cell statistics for position samples from the last hour. The overview visual-density toggle is independent.
- Geofences: built-in and persistent custom polygon zones, plus recent aircraft inside a selected zone. Analysts/admins can save and deactivate custom zones. Built-in zone names are examples, not authoritative airspace information.
- Live Feed: on-demand OpenSky snapshots without storing history. Admins can save a bounded snapshot from Operations or trigger the full scheduled ingestion.
- Aircraft: session trajectories and aircraft-specific alert history. Alerts also shows backend severity totals.

For an existing database, run `python -m scripts.add_geofences` from `backend` using its virtual environment before starting the updated backend. This creates the geofence table without changing other data. Run the existing ground-status migration if it has not already been applied.

New zones take effect in the next anomaly-detection run. Existing alerts are retained when a zone is deactivated. Radius and viewport queries return limited recent snapshots; the UI flags a reached limit. Neither query triggers ingestion itself.
