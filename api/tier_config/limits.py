"""
Tier configuration for the Monte Carlo simulation platform.
Supports flexible multi-tier structure for future expansion.
"""

TIER_LIMITS = {
    'FREE': {
        'display_name': 'Free',
        'description': 'Evaluation access for FIRE community members',
        'max_simulations': 5,
        'max_strategies': 3,
        'features': {
            'basic_simulations': True,
            'custom_strategies': True,
            'pdf_reports': True,
            'ai_analysis': True,
            'strategy_evaluations': True,
            'leaderboard_access': True,
            'priority_support': False,
            'api_access': False,
        },
        'color': '#6B7280',  # Gray for UI display
        'badge': '🆓',
    },
    
    'PAID': {
        'display_name': 'Pro',
        'description': 'For serious FIRE planners',
        'max_simulations': 100,
        'max_strategies': 50,
        'features': {
            'basic_simulations': True,
            'custom_strategies': True,
            'pdf_reports': True,
            'ai_analysis': True,
            'strategy_evaluations': True,
            'leaderboard_access': True,
            'priority_support': True,
            'api_access': False,
        },
        'color': '#3B82F6',  # Blue
        'badge': '⭐',
        'price_sek_monthly': 50,
        'price_sek_annual': 500,
    },
    
    'UNLIMITED': {
        'display_name': 'Unlimited',
        'description': 'For power users and researchers',
        'max_simulations': float('inf'),
        'max_strategies': float('inf'),
        'features': {
            'basic_simulations': True,
            'custom_strategies': True,
            'pdf_reports': True,
            'ai_analysis': True,
            'strategy_evaluations': True,
            'leaderboard_access': True,
            'priority_support': True,
            'api_access': True,
        },
        'color': '#8B5CF6',  # Purple
        'badge': '💎',
        'price_sek_monthly': 200,
        'price_sek_annual': 2000,
    },
    
    'WHITELABEL': {
        'display_name': 'White Label',
        'description': 'For financial advisors and consultants',
        'max_simulations': float('inf'),
        'max_strategies': float('inf'),
        'features': {
            'basic_simulations': True,
            'custom_strategies': True,
            'pdf_reports': True,
            'ai_analysis': True,
            'strategy_evaluations': True,
            'leaderboard_access': True,
            'priority_support': True,
            'api_access': True,
            'custom_branding': True,
            'bulk_export': True,
            'client_management': True,
        },
        'color': '#10B981',  # Green
        'badge': '🏢',
        'price_sek_monthly': None,  # Custom pricing
    },
}

# Default tier for new users
DEFAULT_TIER = 'FREE'

# Tiers that don't require payment (for system use)
FREE_TIERS = ['FREE']

# Admin-only tiers (cannot self-upgrade)
ADMIN_ONLY_TIERS = ['WHITELABEL']
