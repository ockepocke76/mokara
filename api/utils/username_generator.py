"""
Username Generator for Public Display Names

Generates fun, finance-themed usernames for users to replace email addresses
in public contexts (leaderboards, published strategies, etc.).

Format: [Adjective] [Noun]
Examples: "Bullish Warrior", "YOLO Ape", "Diamond Ninja"
"""

import random
from typing import Optional


# Professional/Serious Finance Terms
PROFESSIONAL_ADJECTIVES = [
    "Aggressive", "Balanced", "Bullish", "Bearish", "Conservative",
    "Diversified", "Efficient", "Frugal", "Golden", "Legendary",
    "Optimal", "Prudent", "Resilient", "Savvy", "Strategic",
    "Tactical", "Trinity", "Volatile", "Wealthy", "Wise",
    "Alpha", "Beta", "Diamond", "Platinum", "Elite",
    "Premium", "Superior", "Advanced", "Expert", "Master",
]

PROFESSIONAL_NOUNS = [
    "Accumulator", "Advisor", "Collector", "Commander", "Crusader",
    "Defender", "Guardian", "Hunter", "Investor", "Keeper",
    "Navigator", "Oracle", "Pathfinder", "Pioneer", "Sage",
    "Samurai", "Sentinel", "Strategist", "Trader", "Warrior",
    "Wizard", "Baron", "Captain", "Chief", "General",
    "Architect", "Analyst", "Visionary", "Champion", "Legend",
]

# Fun/Silly Modern Terms
FUN_ADJECTIVES = [
    "YOLO", "HODL", "Degen", "Ape", "Moon",
    "Rocket", "Stonk", "Tendie", "Gigabrain", "Based",
    "Chad", "Sigma", "Legendary", "Epic", "Absolute",
    "Mega", "Ultra", "Super", "Hyper", "Quantum",
    "Turbo", "Infinite", "Maximum", "Supreme", "Cosmic",
]

FUN_NOUNS = [
    "Ape", "Degen", "Gambler", "Believer", "Bro",
    "Enjoyer", "Enthusiast", "Fanatic", "Holder", "Maximalist",
    "Chaser", "Hunter", "Seeker", "Dreamer", "Visionary",
    "Legend", "Hero", "Boss", "King", "Emperor",
    "Genius", "Wizard", "Ninja", "Samurai", "Warrior",
]

# Combine all lists
ALL_ADJECTIVES = PROFESSIONAL_ADJECTIVES + FUN_ADJECTIVES
ALL_NOUNS = PROFESSIONAL_NOUNS + FUN_NOUNS


def generate_username(check_exists_fn: Optional[callable] = None, max_attempts: int = 10) -> str:
    """
    Generate a unique random username.
    
    Args:
        check_exists_fn: Function that checks if username exists (returns bool)
        max_attempts: Number of attempts before adding numeric suffix
        
    Returns:
        Generated username string
    """
    for _ in range(max_attempts):
        adjective = random.choice(ALL_ADJECTIVES)
        noun = random.choice(ALL_NOUNS)
        username = f"{adjective} {noun}"
        
        # Check uniqueness if function provided
        if check_exists_fn is None or not check_exists_fn(username):
            return username
    
    # Fallback: add number suffix
    base_adjective = random.choice(ALL_ADJECTIVES)
    base_noun = random.choice(ALL_NOUNS)
    base = f"{base_adjective} {base_noun}"
    
    counter = 2
    while check_exists_fn and check_exists_fn(f"{base} {counter}"):
        counter += 1
    
    return f"{base} {counter}"


def is_valid_username(username: str) -> tuple[bool, str]:
    """
    Validate a custom username.
    
    Args:
        username: Username string to validate
        
    Returns:
        (is_valid, error_message) tuple
    """
    # Check length
    if not username or len(username.strip()) == 0:
        return False, "Username cannot be empty"
    
    if len(username) > 30:
        return False, "Username must be 30 characters or less"
    
    # Check characters (alphanumeric + spaces only)
    if not all(c.isalnum() or c.isspace() for c in username):
        return False, "Username can only contain letters, numbers, and spaces"
    
    # Check for excessive spaces
    if "  " in username:
        return False, "Username cannot contain consecutive spaces"
    
    if username.startswith(" ") or username.endswith(" "):
        return False, "Username cannot start or end with spaces"
    
    return True, ""


def normalize_username(username: str) -> str:
    """
    Normalize username for case-insensitive comparison.
    
    Args:
        username: Username string
        
    Returns:
        Normalized lowercase version
    """
    return username.strip().lower()


if __name__ == "__main__":
    # Test generation
    print("Sample usernames:")
    for i in range(10):
        print(f"{i+1}. {generate_username()}")
