"""
Pydantic models for database entities.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from src.core.constants import AssetType, Currency, RiskLevel


class UserNote(BaseModel):
    """Model for user investment notes."""

    id: Optional[str] = Field(default=None, description="Note ID")
    user_id: str = Field(description="User ID")
    content: str = Field(description="Note content")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    tags: list[str] = Field(default_factory=list, description="Tags for categorization")

    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "user_id": "user_123",
                "content": "Планую купити квартиру в Києві через 2 роки",
                "tags": ["нерухомість", "довгостроковий"],
            }
        }


class PortfolioAsset(BaseModel):
    """Model for portfolio asset."""

    id: Optional[str] = Field(default=None, description="Asset ID")
    user_id: str = Field(description="User ID")
    asset_type: AssetType = Field(description="Type of asset")
    amount: float = Field(gt=0, description="Amount of asset")
    currency: Currency = Field(description="Currency of asset")
    purchase_date: datetime = Field(description="Date of purchase")
    purchase_price: Optional[float] = Field(default=None, description="Price per unit at purchase")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    notes: Optional[str] = Field(default=None, description="Additional notes about the asset")

    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "user_id": "user_123",
                "asset_type": "ОВДП",
                "amount": 5000,
                "currency": "UAH",
                "purchase_date": "2024-01-01",
                "purchase_price": 100,
            }
        }


class UserProfile(BaseModel):
    """Model for user profile information."""

    id: str = Field(description="User ID")
    email: str = Field(description="User email")
    name: Optional[str] = Field(default=None, description="User full name")
    risk_level: RiskLevel = Field(
        default=RiskLevel.MODERATE, description="Investor risk profile"
    )
    investment_experience: str = Field(
        default="beginner", description="Investment experience level (beginner, intermediate, advanced)"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "id": "user_123",
                "email": "user@example.com",
                "name": "Іван Петренко",
                "risk_level": "Помірний",
                "investment_experience": "intermediate",
            }
        }


class ChatMessage(BaseModel):
    """Model for chat message in conversation."""

    id: Optional[str] = Field(default=None, description="Message ID")
    user_id: str = Field(description="User ID")
    role: str = Field(description="Role of sender (user or assistant)")
    content: str = Field(description="Message content")
    sources: list[str] = Field(default_factory=list, description="Links to source documents")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "user_id": "user_123",
                "role": "user",
                "content": "Що зараз відбувається з податками на інвестиції?",
            }
        }

