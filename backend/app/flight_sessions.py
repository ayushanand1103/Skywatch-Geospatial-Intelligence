"""Infer observed flight sessions; tracking gaps are not confirmed takeoffs."""
from datetime import timedelta
from .models import AircraftPosition

GAP = timedelta(hours=2)

def group_positions(positions):
    groups = []
    for position in positions:
        if position.position is None:
            continue
        previous = groups[-1][-1] if groups else None
        # A new airborne observation after a ground observation starts a new session.
        if previous is None or position.created_at - previous.created_at > GAP or (previous.on_ground is True and position.on_ground is False):
            groups.append([])
        groups[-1].append(position)
    return groups

def aircraft_sessions(db, aircraft_id, since):
    positions = db.query(AircraftPosition).filter(
        AircraftPosition.aircraft_id == aircraft_id,
        AircraftPosition.created_at >= since,
    ).order_by(AircraftPosition.created_at, AircraftPosition.id).all()
    return group_positions(positions)
