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
