import google.genai as genai
from google.genai import types

import requests
import io
import httpx
from dotenv import load_dotenv
import os

from gemeni_cache import create_new_cache

load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")
if api_key is None: 
    print("GOOGLE_API_KEY is not set")
client = genai.Client(api_key=api_key)


def get_cache_name():

    # file to store the cache name
    cache_file = "cache_name.txt"
    cache_name = ""

    # Check if cache name is already saved
    if os.path.exists(cache_file):
        with open(cache_file, 'r') as f:
            cache_name = f.read().strip()
            print(f"Using existing cache: {cache_name}")
            
    else:
        create_new_cache()

    return cache_name



def gemini_prompt(query):
   # Generate content using the cached prompt and document
    response = client.models.generate_content(
    model=model_name,
    contents=query,
    config=types.GenerateContentConfig(
            cached_content=get_cache_name()
            #cached_content=cache.name
    )) 
    return response.text



def test_queries():
    queries = [
        "Tell me something about you.",
        "Tell me a joke",
        "what do you think about quantum physics ?",
        "Tell me about your mom",
        "What is a Plantoid?",
        "How does a Plantoid work?",
        "explain in details how the plantoid works",
        "what's the relationship between plantoids and extitutional theory?",
        "What is an Aminal?",
        "What's your relationship with Aminals?",
        "tell me what brought you to do art in the first place?",
        "tell me more",
        "What is a Network Nations?"
    ]
    for query in queries:
        print(f"\nQuery: {query}")


    # Generate content using the cached prompt and document
    response = client.models.generate_content(
    model=model_name,
    contents=query,
    config=types.GenerateContentConfig(
            cached_content=get_cache_name()
            #cached_content=cache.name
    ))

    # (Optional) Print usage metadata for insights into the API call
    # print(f'{response.usage_metadata=}')

    # Print the generated text
    print('\n\n', response.text)