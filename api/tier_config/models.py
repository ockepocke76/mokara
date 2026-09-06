from dataclasses import dataclass, field
from typing import Dict, Optional

@dataclass(frozen=True)
class TierFeatures:
    """Features enabled for a specific tier."""
    can_use_custom_strategies: bool = False
    can_access_leaderboard: bool = True
    priority_support: bool = False
    api_access: bool = False
    view_demos: bool = False
    view_public_content: bool = False
    download_demo_pdfs: bool = False
    custom_branding: bool = False
    bulk_export: bool = False
    client_management: bool = False
    admin_dashboard: bool = False

@dataclass(frozen=True)
class Tier:
    """Definition of a subscription tier."""
    id: str  # e.g., 'FREE', 'PRO'
    name: str # Display name
    description: str
    
    # Pricing (SEK)
    price_monthly: int
    price_yearly: int
    
    # Limits
    max_simulations: int
    max_strategies: int
    max_pdf_downloads: int
    max_mc_iterations_builtin: int
    max_mc_iterations_custom: int
    ai_generation_credits_monthly: int
    simulation_retention_days: Optional[int] # None = Unlimited
    
    # Features
    features: TierFeatures
    
    # UI
    badge: str
    color: str
    recommended: bool = False

    @property
    def is_unlimited(self) -> bool:
        return self.max_simulations >= 999999
