import openai
import json
import logging
from typing import List, Dict, Optional, Generator
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class Message:
    role: str
    content: str
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
            
    def to_dict(self):
        return {
            "role": self.role,
            "content": self.content
        }


class ConversationManager:
    def __init__(self, api_key: str, personality_config: dict):
        self.client = openai.OpenAI(api_key=api_key)
        self.personality = personality_config
        self.messages: List[Message] = []
        self.model = "gpt-4-turbo-preview"
        
        # Initialize with system message
        system_msg = Message(
            role="system",
            content=self.personality.get("system_message", "You are a helpful assistant.")
        )
        self.messages.append(system_msg)
        
    def add_user_message(self, content: str):
        """Add a user message to the conversation"""
        msg = Message(role="user", content=content)
        self.messages.append(msg)
        logger.info(f"User: {content}")
        
    def generate_response(self, streaming: bool = True) -> Generator[str, None, None]:
        """Generate AI response, optionally streaming"""
        conv_style = self.personality.get("conversation_style", {})
        
        # Prepare messages for API
        api_messages = [msg.to_dict() for msg in self.messages]
        
        try:
            if streaming:
                # Stream response
                stream = self.client.chat.completions.create(
                    model=self.model,
                    messages=api_messages,
                    temperature=conv_style.get("temperature", 0.7),
                    max_tokens=conv_style.get("max_response_length", 150),
                    stream=True
                )
                
                full_response = ""
                for chunk in stream:
                    if chunk.choices[0].delta.content:
                        text = chunk.choices[0].delta.content
                        full_response += text
                        yield text
                        
                # Add complete response to history
                self.messages.append(Message(role="assistant", content=full_response))
                logger.info(f"Assistant: {full_response}")
                
            else:
                # Non-streaming response
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=api_messages,
                    temperature=conv_style.get("temperature", 0.7),
                    max_tokens=conv_style.get("max_response_length", 150)
                )
                
                content = response.choices[0].message.content
                self.messages.append(Message(role="assistant", content=content))
                logger.info(f"Assistant: {content}")
                yield content
                
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            yield "I'm sorry, I encountered an error generating a response."
            
    def get_thinking_sound(self) -> str:
        """Get a random thinking sound"""
        import random
        sounds = self.personality.get("conversation_style", {}).get("thinking_sounds", ["Hmm..."])
        return random.choice(sounds)
        
    def get_interruption_acknowledgment(self) -> str:
        """Get interruption acknowledgment phrase"""
        return self.personality.get("conversation_style", {}).get(
            "interruption_acknowledgment", 
            "Oh, go ahead!"
        )
        
    def clear_history(self, keep_system: bool = True):
        """Clear conversation history"""
        if keep_system and self.messages:
            self.messages = [self.messages[0]]  # Keep only system message
        else:
            self.messages = []
            
    def get_conversation_summary(self) -> str:
        """Get a summary of the conversation"""
        user_messages = [m for m in self.messages if m.role == "user"]
        assistant_messages = [m for m in self.messages if m.role == "assistant"]
        
        return f"Conversation summary: {len(user_messages)} user messages, {len(assistant_messages)} assistant responses"