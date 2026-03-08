"""SQLAlchemy ORM models for the geoshard spatial index."""

from sqlalchemy import BigInteger, Column, DateTime, Index, Numeric, String

from shared.database import Base


class GeoshardEntry(Base):
    __tablename__ = "geoshard_index"

    id = Column(String, primary_key=True)
    entity_id = Column(String, nullable=False)
    entity_type = Column(String(20), nullable=False)  # 'profile' or 'listing'
    geohash = Column(String(12), nullable=False)
    s2_cell_id = Column(BigInteger, nullable=False)
    latitude = Column(Numeric(10, 7), nullable=False)
    longitude = Column(Numeric(10, 7), nullable=False)
    parish = Column(String(50), nullable=True)
    is_active = Column(String(5), default="true")
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_geoshard_hash", "geohash"),
        Index("idx_geoshard_s2", "s2_cell_id"),
        Index("idx_geoshard_entity", "entity_id", "entity_type", unique=True),
        Index("idx_geoshard_parish", "parish"),
    )
