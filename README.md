# SkyWatch Geospatial Intelligence

SkyWatch is a prototype air-traffic intelligence dashboard. It combines recent aircraft positions, trajectories, anomaly alerts, spatial searches, H3 density, geofences, and an experimental Kalman-filter ETA estimate.

## Start the prototype

Requirements: Windows PowerShell and Docker Desktop.

1. Copy `backend/.env.example` to `backend/.env` if the local environment file does not exist. Replace `JWT_SECRET_KEY` with a random value of at least 32 characters. OpenSky OAuth credentials are optional.
2. From the repository root, run:

   ```powershell
   .\start-skywatch.ps1
   ```

3. Open <http://127.0.0.1:5173>. API documentation is available at <http://127.0.0.1:8000/docs>.

The startup script starts PostgreSQL, applies the prototype schema updates, launches the API and frontend, and checks that both respond. Logs are written to `.run`.

Stop the prototype without deleting its database:

```powershell
.\stop-skywatch.ps1
```

## Suggested demo flow

1. Open **Overview** and explain that all headline counts and map aircraft use a rolling one-hour activity window.
2. Select an aircraft marker to show its identity, current state, and trajectory.
3. Open **Spatial Explorer**, enter a point and radius, and show aircraft currently inside it.
4. Open **Density** to show unique active aircraft grouped into H3 hexagons.
5. Open **Alerts** and **Geofences** to demonstrate recent anomaly and boundary events.
6. Open **ETA Predictor**, choose an aircraft with several recent positions, and enter destination coordinates. The estimate appears only when the filtered track is moving toward the destination.

## Traffic density forecast

The authenticated forecast endpoint groups stored positions into completed time intervals, counts distinct aircraft in each interval, and applies ARIMA to predict upcoming traffic density:

```text
GET /api/forecast/density?hours=24&interval_minutes=15&steps=8
GET /api/forecast/density?bbox=70,20,90,35&hours=24&interval_minutes=15&steps=8
GET /api/forecast/density?h3_cell_id=872830828ffffff&hours=24&steps=8
```

If the selected area has too little varied history for a stable ARIMA fit, the response explicitly reports `MOVING_AVERAGE` and `fallback`. For the presentation: “SkyWatch groups aircraft records into fixed time intervals, counts distinct aircraft in each interval, and applies ARIMA to forecast whether an airspace region may become busy in the next few time steps.” Collect at least 2–4 hours of 15-minute observations for a useful demonstration; longer histories generally produce a stronger pattern.

The live OpenSky scheduler defaults to one global request every 15 minutes, or about 384 credits per day at the current four-credit global request cost. Avoid repeated manual live refreshes during the demo. Internet access is required for OpenStreetMap tiles and new OpenSky data; already stored positions remain available if the feed is temporarily unavailable.

## Demo notes

- ETA is an experimental constant-velocity estimate, not an operational arrival prediction.
- An aircraft needs at least two distinct recorded positions for a trajectory or ETA.
- Local data persists between starts in the Docker volume.
- See `frontend/README.md` for the frontend feature guide.
