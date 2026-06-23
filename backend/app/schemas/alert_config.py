"""Alert configuration schemas for manual editing."""
from typing import Optional
from pydantic import BaseModel, Field


class AlertSettingsUpdate(BaseModel):
    """Update alert threshold settings."""
    confidence_threshold: Optional[float] = Field(None, ge=0.0, le=1.0, description="Face recognition confidence threshold (0.0-1.0)")
    liveness_threshold: Optional[float] = Field(None, ge=0.0, le=1.0, description="Anti-spoof liveness threshold (0.0-1.0)")
    cooldown_minutes: Optional[int] = Field(None, ge=1, le=120, description="Cooldown between detections per person per camera (minutes)")
    after_hours_buffer_min: Optional[int] = Field(None, ge=0, le=240, description="Buffer minutes outside shift before after-hours alert (0-240)")
    loitering_threshold_min: Optional[int] = Field(None, ge=1, le=120, description="Minutes near camera before loitering alert (1-120)")
    slack_webhook_url: Optional[str] = Field(None, max_length=2048, description="Slack webhook URL for VIP/blacklist notifications")
    smtp_host: Optional[str] = Field(None, max_length=255, description="SMTP host for email alerts")
    smtp_port: Optional[int] = Field(None, ge=1, le=65535, description="SMTP port")
    smtp_user: Optional[str] = Field(None, max_length=255, description="SMTP username")
    smtp_password: Optional[str] = Field(None, max_length=255, description="SMTP password")
    alert_email_to: Optional[str] = Field(None, max_length=255, description="Email address for alert notifications")
    event_retention_days: Optional[int] = Field(None, ge=1, le=365, description="Days to retain face data (GDPR compliance)")


class BlacklistEmployeeUpdate(BaseModel):
    """Update employee blacklist status."""
    is_blacklisted: bool = Field(..., description="Set employee as blacklisted or remove from blacklist")
    notes: Optional[str] = Field(None, max_length=1000, description="Reason for blacklist")


class RestrictedCameraUpdate(BaseModel):
    """Update camera restricted area status."""
    is_restricted: bool = Field(..., description="Set camera as restricted or remove restriction")


class AdminPasswordCheck(BaseModel):
    """Verify admin password before allowing configuration changes."""
    password: str = Field(..., min_length=8, max_length=255, description="Admin password for configuration changes")


class AdminConfigPasswordIn(BaseModel):
    """Change the alert-config admin password (requires current password for verification)."""
    old_password: str = Field(..., min_length=1, max_length=255)
    new_password: str = Field(..., min_length=8, max_length=255)