import openai
import json
import logging
from typing import List, Dict, Optional, Generator
from dataclasses import dataclass
from datetime import datetime
import google.genai as genai
from google.genai import types
import os
import sys
import re
import signal
import threading
import time

from gemini_cache import get_gemini_cache, create_new_cache

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
            content=self.personality.get("system_message", "You are Primavera De Filippi.")
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
        print ("conv style == " , conv_style)
        
        # Prepare messages for API
        api_messages = [msg.to_dict() for msg in self.messages]
        print ("API msg = ", api_messages)
        
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


class GeminiConversationManager:
    def __init__(self, api_key: str, personality_config: dict = None):
        self.client = genai.Client(api_key=api_key)
        self.model_name = "gemini-2.0-flash"
        self.personality = personality_config or {}
        self.messages: List[Message] = []
        
        # Get cache name for Primavera context
        self.cache_name = get_gemini_cache()
        
    def _generate_with_timeout(self, conversation_context: str, timeout: float):
        """Generate response with timeout protection using threading"""
        result = [None]
        exception = [None]
        
        def generate_response():
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=conversation_context,
                    config=types.GenerateContentConfig(
                        cached_content=self.cache_name
                    )
                )
                result[0] = response
            except Exception as e:
                exception[0] = e
        
        # Start the generation in a separate thread
        thread = threading.Thread(target=generate_response)
        thread.daemon = True
        thread.start()
        
        # Wait for completion with timeout
        thread.join(timeout)
        
        if thread.is_alive():
            # Thread is still running, timeout occurred
            logger.warning(f"Gemini API call timed out after {timeout} seconds")
            return None
            
        if exception[0]:
            raise exception[0]
            
        return result[0]
        
    # def _get_cache_name(self):
    #     """Get cache name from file or create new cache"""
    #     cache_file = "../cache_name.txt"
    #     cache_name = ""
        
    #     if os.path.exists(cache_file):
    #         with open(cache_file, 'r') as f:
    #             cache_name = f.read().strip()
    #             logger.info(f"Using existing cache: {cache_name}")
    #     else:
    #         logger.info("Cache file not found. Creating new cache...")
    #         cache_name = create_new_cache()
            
    #     return cache_name
        
    def add_user_message(self, content: str):
        """Add a user message to the conversation"""
        msg = Message(role="user", content=content)
        self.messages.append(msg)
        logger.info(f"User: {content}")
        
    def generate_response(self, streaming: bool = True, timeout: float = 30.0) -> Generator[str, None, None]:
        """Generate AI response using Gemini with timeout protection"""
        if not self.messages:
            return
            
        # Build conversation context from message history
        conversation_context = ""
        for msg in self.messages:
            if msg.role == "user":
                conversation_context += f"User: {msg.content}\n"
            elif msg.role == "assistant":
                conversation_context += f"Assistant: {msg.content}\n"
        
        # Add instruction for current response
        conversation_context += "Assistant:"
        
        try:
            # Generate response using cached Gemini model with timeout protection
            response = self._generate_with_timeout(conversation_context, timeout)
            
            if response is None:
                # Timeout occurred
                error_msg = "I'm sorry, I was a bit distracted. Can you please repeat?"
                assistant_msg = Message(role="assistant", content=error_msg)
                self.messages.append(assistant_msg)
                yield error_msg
                return
            
            response_text = response.text

            logger.info(f"PRE-FILTERED RESPONSE: {response_text}")

            # Remove text within parentheses or asterisks
            #response_text = re.sub(r'\(.*?\)', '', response_text)
            response_text = re.sub(r'\(.*?\)|\*.*?\*', '', response_text)


            # Cut off text after a paragraph starting with "User:"
            #response_text = re.split(r'\nUser:.*', response_text)[0]
            response_text = re.split(r'(?:\r?\n|^)User:.*', response_text)[0]
        
            
            # Add response to conversation history
            assistant_msg = Message(role="assistant", content=response_text)
            self.messages.append(assistant_msg)
            logger.info(f"Assistant: {response_text}")
            
            # For streaming, yield the entire response at once
            # (Gemini doesn't support true streaming in this setup)
            if streaming:
                yield response_text
            else:
                return response_text
                
        except Exception as e:
            if "403 PERMISSION_DENIED" in str(e):
                logger.error("Cache not found or permission denied. Creating a new cache.")
                self.cache_name = create_new_cache()  # Create a new cache

                # Retry the operation with the new cache
                # yield from self.generate_response(streaming)

                error_msg = "I'm sorry, I didn't hear what you said. Can you please repeat?"
                assistant_msg = Message(role="assistant", content=error_msg)
                self.messages.append(assistant_msg)
                yield error_msg
                
            elif "timeout" in str(e).lower():
                logger.error(f"Gemini API timeout: {e}")
                error_msg = "I'm sorry, I missed what you just said. What was it?"
                assistant_msg = Message(role="assistant", content=error_msg)
                self.messages.append(assistant_msg)
                yield error_msg

            else:
                logger.error(f"Gemini API error: {e}")
                error_msg = "I'm sorry, I have some stuff to deal with. Please call me back later."
                assistant_msg = Message(role="assistant", content=error_msg)
                self.messages.append(assistant_msg)
                yield error_msg
            
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
        self.messages = []
            
    def get_conversation_summary(self) -> str:
        """Get a summary of the conversation"""
        user_messages = [m for m in self.messages if m.role == "user"]
        assistant_messages = [m for m in self.messages if m.role == "assistant"]
        
        return f"Conversation summary: {len(user_messages)} user messages, {len(assistant_messages)} assistant responses"