#!/usr/bin/env python3
"""
Layer Pattern Management Utility

This script helps manage the dynamic layer pattern matching configuration.
You can use it to add, remove, or view layer patterns without manually editing the JSON file.
"""

import json
import os
import sys
from pathlib import Path


class LayerPatternManager:
    def __init__(self, config_path=None):
        if config_path is None:
            config_path = Path(__file__).parent / 'layer_patterns_config.json'
        self.config_path = config_path
        self.config = self.load_config()
    
    def load_config(self):
        """Load the configuration from JSON file."""
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error loading config: {e}")
            return self.create_default_config()
    
    def save_config(self):
        """Save the configuration to JSON file."""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
            print(f"✅ Configuration saved to {self.config_path}")
            return True
        except Exception as e:
            print(f"❌ Error saving config: {e}")
            return False
    
    def create_default_config(self):
        """Create a default configuration."""
        return {
            "layer_pattern_config": {
                "location_patterns": {},
                "terrain_patterns": {},
                "data_type_patterns": {},
                "temporal_patterns": {},
                "resolution_patterns": {}
            },
            "fallback_patterns": ["mosaic", "composite"],
            "exact_match_priority": True,
            "case_sensitive": False
        }
    
    def add_pattern(self, category, search_term, matches):
        """Add a new pattern to the configuration."""
        if category not in self.config["layer_pattern_config"]:
            self.config["layer_pattern_config"][category] = {}
        
        self.config["layer_pattern_config"][category][search_term] = matches
        print(f"✅ Added: {category}.{search_term} -> {matches}")
        return self.save_config()
    
    def remove_pattern(self, category, search_term):
        """Remove a pattern from the configuration."""
        try:
            del self.config["layer_pattern_config"][category][search_term]
            print(f"✅ Removed: {category}.{search_term}")
            return self.save_config()
        except KeyError:
            print(f"❌ Pattern not found: {category}.{search_term}")
            return False
    
    def list_patterns(self, category=None):
        """List all patterns or patterns in a specific category."""
        if category:
            if category in self.config["layer_pattern_config"]:
                patterns = self.config["layer_pattern_config"][category]
                print(f"\n📂 {category.upper()}:")
                for search_term, matches in patterns.items():
                    print(f"  {search_term} -> {matches}")
            else:
                print(f"❌ Category '{category}' not found")
        else:
            print("\n📋 ALL PATTERNS:")
            for cat, patterns in self.config["layer_pattern_config"].items():
                print(f"\n📂 {cat.upper()}:")
                for search_term, matches in patterns.items():
                    print(f"  {search_term} -> {matches}")
            
            print(f"\n🔄 FALLBACK PATTERNS: {self.config['fallback_patterns']}")
            print(f"⚙️  CASE SENSITIVE: {self.config['case_sensitive']}")
    
    def add_fallback(self, pattern):
        """Add a fallback pattern."""
        if pattern not in self.config["fallback_patterns"]:
            self.config["fallback_patterns"].append(pattern)
            print(f"✅ Added fallback: {pattern}")
            return self.save_config()
        else:
            print(f"⚠️  Fallback '{pattern}' already exists")
            return True
    
    def remove_fallback(self, pattern):
        """Remove a fallback pattern."""
        try:
            self.config["fallback_patterns"].remove(pattern)
            print(f"✅ Removed fallback: {pattern}")
            return self.save_config()
        except ValueError:
            print(f"❌ Fallback '{pattern}' not found")
            return False
    
    def test_pattern(self, requested_layer, available_layers):
        """Test pattern matching with given layers."""
        print(f"\n🧪 TESTING PATTERN MATCHING")
        print(f"Requested: '{requested_layer}'")
        print(f"Available: {available_layers}")
        
        # Simulate the pattern matching logic
        layer_patterns = self.config.get("layer_pattern_config", {})
        case_sensitive = self.config.get("case_sensitive", False)
        fallback_patterns = self.config.get("fallback_patterns", [])
        
        if case_sensitive:
            layer_search = requested_layer
            available_normalized = available_layers
        else:
            layer_search = requested_layer.lower()
            available_normalized = [layer.lower() for layer in available_layers]
        
        # Test configured patterns
        for category_name, patterns in layer_patterns.items():
            for search_term, possible_matches in patterns.items():
                if search_term in layer_search:
                    for i, avail_layer_norm in enumerate(available_normalized):
                        for match_term in possible_matches:
                            if match_term in avail_layer_norm:
                                original_layer = available_layers[i]
                                print(f"✅ MATCH: {category_name}.{search_term} -> '{original_layer}' (via '{match_term}')")
                                return original_layer
        
        # Test fallback patterns
        for fallback in fallback_patterns:
            for i, avail_layer_norm in enumerate(available_normalized):
                if fallback in avail_layer_norm:
                    original_layer = available_layers[i]
                    print(f"✅ FALLBACK MATCH: '{fallback}' -> '{original_layer}'")
                    return original_layer
        
        print("❌ NO MATCH FOUND")
        return None


def main():
    manager = LayerPatternManager()
    
    if len(sys.argv) < 2:
        print("""
🔧 Layer Pattern Management Utility

Usage:
  python layer_pattern_manager.py <command> [arguments]

Commands:
  list [category]                    - List all patterns or patterns in category
  add <category> <search> <matches>  - Add new pattern (matches as comma-separated)
  remove <category> <search>         - Remove pattern
  add-fallback <pattern>             - Add fallback pattern
  remove-fallback <pattern>          - Remove fallback pattern
  test <requested> <available>       - Test pattern matching (available as comma-separated)

Categories: location_patterns, terrain_patterns, data_type_patterns, temporal_patterns, resolution_patterns

Examples:
  python layer_pattern_manager.py list
  python layer_pattern_manager.py add location_patterns pune "pune,mosaic,maharashtra"
  python layer_pattern_manager.py test "delhi_elevation" "delhi_mosaic,mumbai_data,elevation_dem"
""")
        return
    
    command = sys.argv[1].lower()
    
    if command == "list":
        category = sys.argv[2] if len(sys.argv) > 2 else None
        manager.list_patterns(category)
    
    elif command == "add":
        if len(sys.argv) != 5:
            print("❌ Usage: add <category> <search_term> <matches_comma_separated>")
            return
        category, search_term, matches_str = sys.argv[2], sys.argv[3], sys.argv[4]
        matches = [m.strip() for m in matches_str.split(',')]
        manager.add_pattern(category, search_term, matches)
    
    elif command == "remove":
        if len(sys.argv) != 4:
            print("❌ Usage: remove <category> <search_term>")
            return
        category, search_term = sys.argv[2], sys.argv[3]
        manager.remove_pattern(category, search_term)
    
    elif command == "add-fallback":
        if len(sys.argv) != 3:
            print("❌ Usage: add-fallback <pattern>")
            return
        pattern = sys.argv[2]
        manager.add_fallback(pattern)
    
    elif command == "remove-fallback":
        if len(sys.argv) != 3:
            print("❌ Usage: remove-fallback <pattern>")
            return
        pattern = sys.argv[2]
        manager.remove_fallback(pattern)
    
    elif command == "test":
        if len(sys.argv) != 4:
            print("❌ Usage: test <requested_layer> <available_layers_comma_separated>")
            return
        requested = sys.argv[2]
        available = [layer.strip() for layer in sys.argv[3].split(',')]
        manager.test_pattern(requested, available)
    
    else:
        print(f"❌ Unknown command: {command}")


if __name__ == "__main__":
    main()
