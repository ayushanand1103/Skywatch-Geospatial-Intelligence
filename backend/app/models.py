from sqlalchemy import Column, Float,Integer,String,DateTime,ForeignKey,Text,Boolean,JSON,CheckConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from geoalchemy2 import Geography
from datetime import datetime,timezone

Base = declarative_base()

class Aircraft(Base):

    __tablename__ = "aircraft"

    id = Column(Integer, primary_key=True, index = True)
    icao24 = Column(String(20),unique= True, nullable=False,index = True)
    call_sign = Column(String(50))
    aircraft_type = Column(String(100))
    origin_country = Column(String(100))
    last_position = Column(Geography(geometry_type='POINT', srid=4326))
    last_update = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    altitude_meters = Column(Float)
    velocity_mps = Column(Float)
    heading_= Column(Float)
    on_ground = Column(Boolean)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    positions = relationship("AircraftPosition", back_populates="aircraft", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Aircraft(icao24={self.icao24}, call_sign={self.call_sign}, aircraft_type={self.aircraft_type})>"

    

class AircraftPosition(Base):

    __tablename__ = "aircraft_positions"

    id = Column(Integer, primary_key=True, index = True)
    aircraft_id = Column(Integer, ForeignKey("aircraft.id"), nullable=False)
    position = Column(Geography(geometry_type='POINT', srid=4326))
    altitude_meters = Column(Float)
    velocity_mps = Column(Float)
    heading_ = Column(Float)
    h3_cell_id = Column(String(20), index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)) 
    
    aircraft = relationship("Aircraft", back_populates="positions")
    
    def __repr__(self):
        return f"<AircraftPosition {self.aircraft_id} at {self.created_at}>"

class Vessel(Base):

     __tablename__ = "vessels"

     id = Column(Integer,primary_key=True,index=True)
     mmsi = Column(String(20),unique=True,nullable=False,index=True)
     name = Column(String(200))
     vessel_type = Column(String(100))
     flag_country = Column(String(10))
     last_position = Column(Geography('POINT', srid=4326))
     last_update = Column(DateTime(timezone=True))
     speed_knots = Column(Float)
     heading = Column(Float)
     destination = Column(String(255))
     created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))  
    
     positions = relationship("VesselPosition", back_populates="vessel", cascade="all, delete-orphan")
    
     def __repr__(self):
        return f"<Vessel {self.mmsi} - {self.name}>"

class VesselPosition(Base):

    __tablename__ = 'vessel_positions'
    
    id = Column(Integer, primary_key=True, index=True)
    vessel_id = Column(Integer, ForeignKey('vessels.id', ondelete='CASCADE'), nullable=False)
    position = Column(Geography('POINT', srid=4326), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    speed_knots = Column(Float)
    heading = Column(Float)
    h3_cell_id = Column(String(20), index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)) 
    
    vessel = relationship("Vessel", back_populates="positions")

class events(Base):

    __tablename__ = 'events'
    
    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String(100), nullable=False, index=True)
    title = Column(String(500))
    description = Column(Text)
    position = Column(Geography('POINT', srid=4326), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    severity = Column(String(50))
    source = Column(String(100))
    source_url = Column(Text)
    event_metadata = Column("metadata", JSON)
    h3_cell_id = Column(String(20), index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))  # FIX
    
    def __repr__(self):
        return f"<Event {self.event_type} - {self.title}>"

class Alert(Base):
    
    __tablename__ = 'alerts'
    
    id = Column(Integer, primary_key=True, index=True)
    alert_type = Column(String(100), nullable=False, index=True)
    severity = Column(String(20), nullable=False, index=True)
    reason = Column(Text, nullable=False)
    aircraft_icao24 = Column(String(20), index=True)
    aircraft_callsign = Column(String(50))
    aircraft_id = Column(Integer, ForeignKey('aircraft.id', ondelete='SET NULL'), nullable=True)
    position = Column(Geography('POINT', srid=4326), nullable=False)
    detected_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    is_acknowledged = Column(Boolean, default=False)
    details = Column(JSON)
    priority = Column(Integer, default=50)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    def __repr__(self):
        return f"<Alert {self.alert_type} - {self.severity} - {self.aircraft_callsign}>"


class User(Base):
    __tablename__ = 'users'
    __table_args__ = (CheckConstraint("role IN ('viewer', 'analyst', 'admin')", name='users_role_check'),)
    role = Column(String(20), nullable=False, default='viewer', server_default='viewer')

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
