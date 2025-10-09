"""
User Preferences Model
Stores user-specific preferences and settings
"""
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .base import Base


class UserPreference(Base):
    """Model for user preferences and settings"""
    __tablename__ = 'user_preferences'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True)

    # Sync page preferences
    last_selected_server_id = Column(Integer, ForeignKey('servers.id', ondelete='SET NULL'), nullable=True)
    last_selected_team_id = Column(Integer, ForeignKey('teams.id', ondelete='SET NULL'), nullable=True)

    # Additional preferences (JSON for flexibility)
    preferences = Column(JSON, default={})

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship('User', back_populates='preferences')
    last_selected_server = relationship('Server', foreign_keys=[last_selected_server_id])
    last_selected_team = relationship('Team', foreign_keys=[last_selected_team_id])

    def __repr__(self):
        return f"<UserPreference(user_id={self.user_id})>"

    def get_preference(self, key, default=None):
        """Get a preference value"""
        if self.preferences:
            return self.preferences.get(key, default)
        return default

    def set_preference(self, key, value):
        """Set a preference value"""
        if not self.preferences:
            self.preferences = {}
        self.preferences[key] = value