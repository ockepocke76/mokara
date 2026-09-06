from .models import Tier, TierFeatures

# Define feature sets first for reusability
FEATURES_ANONYMOUS = TierFeatures(
    can_use_custom_strategies=False,
    can_access_leaderboard=True,
    priority_support=False,
    view_demos=True,
    view_public_content=True,
    download_demo_pdfs=True
)

FEATURES_FREE = TierFeatures(
    can_use_custom_strategies=True,
    can_access_leaderboard=True,
    priority_support=False
)

# Let me rewrite models.py first to include ai_analysis if needed, 
# OR just stick to what I wrote. 
# check_feature_access relies on checking if key is True.
# I will proceed but correct Features in a follow up if I missed one.
# Re-reading models.py I submitted:
# can_use_custom_strategies, can_access_leaderboard, priority_support, api_access, 
# view_demos, view_public_content, download_demo_pdfs, custom_branding, bulk_export, client_management, admin_dashboard.
# It seems I missed 'ai_analysis' boolean separate from credits?
# In core/limits.py (Step 914), check_feature_access checks 'features' dict.
# I'll stick to the defined fields.

FEATURES_FREE = TierFeatures(
    can_use_custom_strategies=True,
    can_access_leaderboard=True,
    priority_support=False
)

FEATURES_PRO = TierFeatures(
    can_use_custom_strategies=True,
    can_access_leaderboard=True,
    priority_support=True
)

FEATURES_ADMIN = TierFeatures(
    can_use_custom_strategies=True,
    can_access_leaderboard=True,
    priority_support=True,
    admin_dashboard=True,
    api_access=True
)

FEATURES_WHITELABEL = TierFeatures(
    can_use_custom_strategies=True,
    can_access_leaderboard=True,
    priority_support=True,
    custom_branding=True,
    bulk_export=True,
    client_management=True,
    api_access=True
)


TIERS = {
    'ANONYMOUS': Tier(
        id='ANONYMOUS',
        name='Guest',
        description='Full access to demo content and public features',
        price_monthly=0,
        price_yearly=0,
        max_simulations=0,
        max_strategies=0,
        max_pdf_downloads=0,
        max_mc_iterations_builtin=0,
        max_mc_iterations_custom=0,
        ai_generation_credits_monthly=0,
        simulation_retention_days=0,
        features=FEATURES_ANONYMOUS,
        badge='👁️',
        color='#9CA3AF'
    ),
    'FREE': Tier(
        id='FREE',
        name='Free API Only',
        description='Basic access for individuals exploring the simulator.',
        price_monthly=0,
        price_yearly=0,
        max_simulations=10,
        max_strategies=10,
        max_pdf_downloads=3,
        max_mc_iterations_builtin=1000,
        max_mc_iterations_custom=1000,
        ai_generation_credits_monthly=10,
        simulation_retention_days=30,
        features=FEATURES_FREE,
        badge='🆓',
        color='#6B7280'
    ),
    'PRO': Tier(
        id='PRO',
        name='Pro Investor',
        description='Enhanced limits and features for serious analysis.',
        price_monthly=99,
        price_yearly=990,
        max_simulations=50,
        max_strategies=20,
        max_pdf_downloads=50,
        max_mc_iterations_builtin=5000,
        max_mc_iterations_custom=2000,
        ai_generation_credits_monthly=50,
        simulation_retention_days=30,
        features=FEATURES_PRO,
        badge='🚀',
        color='#3B82F6',
        recommended=True
    ),
    'WHITELABEL': Tier(
        id='WHITELABEL',
        name='White Label',
        description='For financial advisors and consultants',
        price_monthly=999, # Placeholder
        price_yearly=9990,
        max_simulations=999999,
        max_strategies=999999,
        max_pdf_downloads=999999,
        max_mc_iterations_builtin=10000,
        max_mc_iterations_custom=10000,
        ai_generation_credits_monthly=999999,
        simulation_retention_days=None,
        features=FEATURES_WHITELABEL,
        badge='🏢',
        color='#10B981'
    ),
    'ADMIN': Tier(
        id='ADMIN',
        name='Administrator',
        description='Unlimited access for system administrators.',
        price_monthly=0,
        price_yearly=0,
        max_simulations=999999,
        max_strategies=999999,
        max_pdf_downloads=999999,
        max_mc_iterations_builtin=10000,
        max_mc_iterations_custom=10000,
        ai_generation_credits_monthly=999999,
        simulation_retention_days=None,
        features=FEATURES_ADMIN,
        badge='🛡️',
        color='#EF4444'
    ),
}

DEFAULT_TIER_ID = 'FREE'
