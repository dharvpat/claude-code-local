"""
Model Capabilities Detection
Automatically detects what tool support each Ollama model has
"""

import json
import logging
from enum import IntEnum
from pathlib import Path
from typing import Dict, Optional, Tuple
import re

logger = logging.getLogger(__name__)


class ModelTier(IntEnum):
    """Model capability tiers for tool support"""
    TIER_1_NATIVE_OPENAI = 1  # Full OpenAI function calling
    TIER_2_PARTIAL = 2         # Some native support, needs prompting
    TIER_3_PROMPT_BASED = 3    # No native support, prompt-based only


class ModelCapabilities:
    """Detect and cache model capabilities"""

    def __init__(self, database_path: Optional[str] = None):
        """
        Initialize model capabilities detector

        Args:
            database_path: Path to model database JSON file
        """
        if database_path is None:
            # Default to same directory as this file
            database_path = Path(__file__).parent / "model_database.json"

        self.database_path = Path(database_path)
        self.database = self._load_database()
        self._cache: Dict[str, Tuple[ModelTier, str, bool]] = {}

        logger.info(f"ModelCapabilities initialized with {len(self.database['models'])} model entries")

    def _load_database(self) -> Dict:
        """Load model database from JSON"""
        try:
            with open(self.database_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading model database: {e}")
            # Return minimal fallback
            return {
                "models": {
                    "*": {
                        "tier": 3,
                        "format": "prompt-based",
                        "supports_native_tools": False,
                        "notes": "Fallback"
                    }
                }
            }

    def get_capabilities(self, model_name: str) -> Tuple[ModelTier, str, bool]:
        """
        Get capabilities for a model

        Args:
            model_name: Name of the Ollama model (e.g., "qwen2.5-coder:7b")

        Returns:
            Tuple of (tier, format, supports_native_tools)
        """
        # Check cache first
        if model_name in self._cache:
            logger.debug(f"Using cached capabilities for {model_name}")
            return self._cache[model_name]

        # Look up in database
        model_info = self._lookup_model(model_name)

        tier = ModelTier(model_info["tier"])
        format_type = model_info["format"]
        supports_native = model_info["supports_native_tools"]

        # Cache result
        self._cache[model_name] = (tier, format_type, supports_native)

        logger.info(
            f"Model {model_name}: Tier {tier.value}, "
            f"Format: {format_type}, Native: {supports_native}"
        )

        return tier, format_type, supports_native

    def _lookup_model(self, model_name: str) -> Dict:
        """
        Look up model in database with pattern matching

        Args:
            model_name: Model name to look up

        Returns:
            Model info dict
        """
        models = self.database.get("models", {})

        # Exact match first
        if model_name in models:
            logger.debug(f"Exact match found for {model_name}")
            return models[model_name]

        # Pattern matching (e.g., "llama3.1:*")
        for pattern, info in models.items():
            if pattern == "*":
                continue  # Save wildcard for last

            # Convert pattern to regex
            regex_pattern = pattern.replace("*", ".*").replace(":", ":")
            if re.match(f"^{regex_pattern}$", model_name):
                logger.debug(f"Pattern match: {model_name} matches {pattern}")
                return info

        # Fallback to wildcard
        logger.debug(f"Using wildcard fallback for {model_name}")
        return models.get("*", {
            "tier": 3,
            "format": "prompt-based",
            "supports_native_tools": False,
            "notes": "Unknown model"
        })

    def get_tier(self, model_name: str) -> ModelTier:
        """Get just the tier for a model"""
        tier, _, _ = self.get_capabilities(model_name)
        return tier

    def supports_native_tools(self, model_name: str) -> bool:
        """Check if model supports native function calling"""
        _, _, supports = self.get_capabilities(model_name)
        return supports

    def get_format(self, model_name: str) -> str:
        """Get the tool format for a model"""
        _, format_type, _ = self.get_capabilities(model_name)
        return format_type

    def is_tier_1(self, model_name: str) -> bool:
        """Check if model is Tier 1 (full OpenAI support)"""
        return self.get_tier(model_name) == ModelTier.TIER_1_NATIVE_OPENAI

    def is_tier_2(self, model_name: str) -> bool:
        """Check if model is Tier 2 (partial support)"""
        return self.get_tier(model_name) == ModelTier.TIER_2_PARTIAL

    def is_tier_3(self, model_name: str) -> bool:
        """Check if model is Tier 3 (prompt-based only)"""
        return self.get_tier(model_name) == ModelTier.TIER_3_PROMPT_BASED

    def get_description(self, model_name: str) -> str:
        """Get human-readable description of model capabilities"""
        tier, format_type, supports_native = self.get_capabilities(model_name)

        descriptions = {
            ModelTier.TIER_1_NATIVE_OPENAI: f"Full OpenAI function calling support ({format_type})",
            ModelTier.TIER_2_PARTIAL: f"Partial tool support ({format_type}), benefits from guided prompts",
            ModelTier.TIER_3_PROMPT_BASED: "No native tool support, using prompt-based approach"
        }

        return descriptions.get(tier, "Unknown capability")

    def add_model(self, model_name: str, tier: int, format_type: str, supports_native: bool, notes: str = ""):
        """
        Add or update a model in the database (runtime only, not persisted)

        Args:
            model_name: Model name or pattern
            tier: Capability tier (1-3)
            format_type: Format identifier
            supports_native: Whether model has native tool support
            notes: Additional notes
        """
        if "models" not in self.database:
            self.database["models"] = {}

        self.database["models"][model_name] = {
            "tier": tier,
            "format": format_type,
            "supports_native_tools": supports_native,
            "notes": notes
        }

        # Invalidate cache for this model
        if model_name in self._cache:
            del self._cache[model_name]

        logger.info(f"Added/updated model: {model_name} (Tier {tier})")

    def clear_cache(self):
        """Clear the capabilities cache"""
        self._cache.clear()
        logger.debug("Cleared capabilities cache")

    def get_all_models(self) -> Dict:
        """Get all models from database"""
        return self.database.get("models", {})

    def get_statistics(self) -> Dict:
        """Get statistics about known models"""
        models = self.get_all_models()

        tier_counts = {1: 0, 2: 0, 3: 0}
        native_count = 0

        for model_info in models.values():
            tier = model_info.get("tier", 3)
            if tier in tier_counts:
                tier_counts[tier] += 1

            if model_info.get("supports_native_tools", False):
                native_count += 1

        return {
            "total_models": len(models),
            "tier_1_models": tier_counts[1],
            "tier_2_models": tier_counts[2],
            "tier_3_models": tier_counts[3],
            "models_with_native_support": native_count,
            "cached_lookups": len(self._cache)
        }
