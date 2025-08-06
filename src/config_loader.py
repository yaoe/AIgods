import json
import os
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class ConfigLoader:
    def __init__(self, config_dir: str = "config"):
        self.config_dir = config_dir
        self.personality = self._load_personality()
        
    def _load_personality(self) -> Dict[str, Any]:
        """Load personality configuration from JSON file"""
        personality_path = os.path.join(self.config_dir, "personality.json")
        
        try:
            with open(personality_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"Personality config not found at {personality_path}, using defaults")
            return self._get_default_personality()
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing personality config: {e}, using defaults")
            return self._get_default_personality()
            
    def _get_default_personality(self) -> Dict[str, Any]:
        """Get default personality configuration"""
        return {
            "name": "Assistant",
            "system_message": "You are a helpful AI assistant engaged in voice conversation.",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True
            },
            "conversation_style": {
                "max_response_length": 150,
                "temperature": 0.7,
                "interruption_acknowledgment": "Yes?",
                "thinking_sounds": ["Hmm...", "Let me think..."]
            }
        }
        
    def update_personality(self, updates: Dict[str, Any]):
        """Update personality configuration"""
        # Deep merge updates
        self._deep_merge(self.personality, updates)
        self._save_personality()
        
    def _deep_merge(self, base: dict, updates: dict):
        """Deep merge dictionaries"""
        for key, value in updates.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value
                
    def _save_personality(self):
        """Save personality configuration to file"""
        personality_path = os.path.join(self.config_dir, "personality.json")
        
        try:
            os.makedirs(self.config_dir, exist_ok=True)
            with open(personality_path, 'w') as f:
                json.dump(self.personality, f, indent=2)
            logger.info("Personality configuration saved")
        except Exception as e:
            logger.error(f"Error saving personality config: {e}")
            
    def get_voice_settings(self) -> Dict[str, Any]:
        """Get voice settings from personality config"""
        return self.personality.get("voice_settings", {})
        
    def get_conversation_style(self) -> Dict[str, Any]:
        """Get conversation style settings"""
        return self.personality.get("conversation_style", {})
        
    def reload(self):
        """Reload configuration from disk"""
        self.personality = self._load_personality()
        logger.info("Configuration reloaded")