#!/usr/bin/env python3
"""
Test script to demonstrate the dynamic layer pattern matching system.
This shows how the system works without hardcoded patterns like "Delhi".
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from test2 import find_layer_by_patterns, load_layer_patterns_config

def test_dynamic_patterns():
    """Test the dynamic pattern matching with various scenarios."""
    
    print("🧪 TESTING DYNAMIC LAYER PATTERN MATCHING")
    print("=" * 50)
    
    # Test scenarios that would have been hardcoded before
    test_cases = [
        {
            "name": "Delhi Pattern Matching",
            "requested": "delhi_elevation",
            "available": ["delhi_mosaic", "mumbai_data", "bangalore_slope"]
        },
        {
            "name": "Mumbai Pattern Matching",
            "requested": "mumbai_satellite",
            "available": ["mumbai_landsat_mosaic", "delhi_elevation", "chennai_aerial"]
        },
        {
            "name": "Terrain Pattern Matching",
            "requested": "slope_analysis",
            "available": ["gradient_mosaic", "elevation_dem", "aspect_data"]
        },
        {
            "name": "Bangalore Alternative Names",
            "requested": "bangalore_roads",
            "available": ["bengaluru_transportation_mosaic", "delhi_data", "mumbai_info"]
        },
        {
            "name": "Fallback Pattern Matching",
            "requested": "unknown_layer",
            "available": ["some_mosaic", "other_composite", "random_data"]
        },
        {
            "name": "No Match Scenario",
            "requested": "nonexistent_layer",
            "available": ["completely_different", "totally_unrelated", "nothing_matches"]
        }
    ]
    
    for test_case in test_cases:
        print(f"\n📋 {test_case['name']}")
        print(f"   Requested: '{test_case['requested']}'")
        print(f"   Available: {test_case['available']}")
        
        result = find_layer_by_patterns(test_case['requested'], test_case['available'])
        
        if result:
            print(f"   ✅ Match found: '{result}'")
        else:
            print(f"   ❌ No match found")

def show_current_config():
    """Show the current pattern configuration."""
    print("\n📋 CURRENT PATTERN CONFIGURATION")
    print("=" * 50)
    
    config = load_layer_patterns_config()
    patterns = config.get("layer_pattern_config", {})
    
    for category, category_patterns in patterns.items():
        print(f"\n📂 {category.upper().replace('_', ' ')}:")
        for search_term, matches in category_patterns.items():
            print(f"   {search_term} → {matches}")
    
    fallbacks = config.get("fallback_patterns", [])
    print(f"\n🔄 FALLBACK PATTERNS: {fallbacks}")
    
    print(f"⚙️  CASE SENSITIVE: {config.get('case_sensitive', False)}")

def demonstrate_adding_patterns():
    """Demonstrate how to add new patterns dynamically."""
    print("\n🔧 DEMONSTRATING DYNAMIC PATTERN ADDITION")
    print("=" * 50)
    
    # Example: Adding a new city pattern
    print("➕ Adding pattern for Pune...")
    from test2 import add_layer_pattern
    
    success = add_layer_pattern(
        "location_patterns", 
        "pune", 
        ["pune", "poona", "mosaic", "maharashtra"]
    )
    
    if success:
        print("✅ Pattern added successfully!")
        
        # Test the new pattern
        test_result = find_layer_by_patterns(
            "pune_elevation", 
            ["poona_height_mosaic", "mumbai_data", "delhi_info"]
        )
        
        if test_result:
            print(f"✅ New pattern works: '{test_result}'")
        else:
            print("❌ New pattern not working")
    else:
        print("❌ Failed to add pattern")

def main():
    """Main test function."""
    print("🚀 DYNAMIC LAYER PATTERN MATCHING DEMO")
    print("This system replaces hardcoded patterns (like Delhi) with configurable ones.")
    print()
    
    # Show current configuration
    show_current_config()
    
    # Test pattern matching
    test_dynamic_patterns()
    
    # Demonstrate adding new patterns
    demonstrate_adding_patterns()
    
    print("\n" + "=" * 50)
    print("✅ DEMO COMPLETE")
    print("Key Benefits:")
    print("- No hardcoded city/location names in code")
    print("- Easily configurable via JSON file")
    print("- Supports multiple pattern categories")
    print("- Fallback patterns for unknown cases")
    print("- Can add new patterns without code changes")

if __name__ == "__main__":
    main()
