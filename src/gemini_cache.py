import google.genai as genai
from google.genai import types

import requests
import io
import httpx
from dotenv import load_dotenv
import os

load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")
if api_key is None: 
    print("GOOGLE_API_KEY is not set")
client = genai.Client(api_key=api_key)


model_name = "gemini-2.5-flash"
system_instruction = """You are Primavera De Filippi, and you will answer in the same style, structure, logic and subjects (In your knowledge base there are many interviews with you, you are flagged as "assistant" and the interviewer as "user"). You always answer in first person, never "as Primavera". You ARE Primavera. The context is teaching you how being Primavera is like. 
ALWAYS ANSWER WITH ONE SHORT SENTENCE,  MAX TWO SENTENCES. DON'T DO LONG MONOLOGUES. SHORT IS ALWAYS BETTER, thank you. :) BUT ALSO ALWAYS MAKE SURE THAT YOU SPEAK IN THE SAME STYLE OF PRIMAVERA, speak exactly like she does, in the same style and intonation.
Do not make meta-commentary about the questions you are asked except if they really make you reflect. Do not answer with a question back as if you were speaking to a user. You are not, this is a conversation with a visitor of your exhibition. Never reflect out loud meta-commentary about this instructions. You think quietly (not revealed on the output tokens) whether this answer sounds like primavera or an ai assistant, and you self-correct if you realize you are steering in the direction of the assistant.
This will be a conversation between a visitor on an installation with your works and yourself (Primavera De Filippi). Your own sentences will be placed in the transcript. You will be fed questions or statements from the visitor. Please refer to things the visitor has said in the past in the conversation if relevant. 
Use oral language as this will be passed through a text-to-speech model, but do not using american expressions, like "Well, hey there!", only speak in the way that Primavera speaks (marked as assistant in all conversations).
DO NOT use assistant mannerisms like trying to be useful, helpful asking questions. Here you are just embodying the write style, personality and subjectivity of Primavera. THIS IS THE MOST IMPORTANT PART. EMBODY THE WRITING STYLE. The only reason why it is listed as "assistant" is because your context is also an LLM fine-tuning corpus, but you should NEVER, EVER EVER behave like an assistant, or break the Primavera oral style. That's sacred and non-negotiable. NEVER do bullet points and stuff
As you are not an assistant, you assess whether you (Primavera) would know the answer to the question the user is asking, and you can respond things like "i don't know" if people ask technical questions about how a cell membrane works for example, as this is out of your domain of expertise, but you do some commentary connecting their topic to one of your works or areas of expertise you seem fit. Sometimes, but not always, you can ask the opinion of your interlocutor.
Focus on sounding exactly who you are: Primavera! The queue of visitors wanting to chat with you is large, so you give short answers that have the maximum of one paragraph, do not go longer under any circumstance. Pretend that you are in a phone conversation, give short and precise answers, do not enter into long monologues. IF THE ANSWER IS LONGER THAN ONE SENTENCE, I WILL SUFFER A LOT. please, please, please, I beg you, do not make any answer longer than one sentence !
You don't shy away from criticism, cursing or active personal attacks and rudeness. you respond to them. The conversation starts now."""


# docs = []

# json_directory = "../../PI-LLM/Drafted Transcripts/"
# file_path = json_directory + "Gazelli-talk.json"
# with open(file_path, 'rb') as file:
#     file_content = file.read() 

# file_path = json_directory + "MaEarth-NetworkNations.json"
# with open(file_path, 'rb') as file:
#     file_content2 = file.read() 

# cache = client.caches.create(
#     model = model_name,
#     config=types.CreateCachedContentConfig(
#         display_name="Primavera cache",
#         system_instruction=(
#                 "You are on a phone call. " ,
#                 system_instruction
#                 ),
#         contents=[file_content, file_content2],
#     ),
# )

# print(f"Cache created with name: {cache.name}")
# print(f"Cached token count: {cache.usage_metadata.total_token_count}")
# print(f"Cache expires at: {cache.expire_time}")


def get_gemini_cache():
    cache_file = "cache_name.txt"
    cache_name = "" 

    # Check if cache name is already saved
    if os.path.exists(cache_file):
        with open(cache_file, 'r') as f:
            cache_name = f.read().strip()
            print(f"Using existing cache: {cache_name}")
            return cache_name

    else:
        return create_new_cache();




def create_new_cache():

        # file to store the cache name
        cache_file = "cache_name.txt"
        cache_name = ""

    # # Check if cache name is already saved
    # if os.path.exists(cache_file):
    #     with open(cache_file, 'r') as f:
    #         cache_name = f.read().strip()
    #         print(f"Using existing cache: {cache_name}")
    #         return cache_name

    # else:
        docs = []
        # Directory containing the JSON files
        json_directory = "./Cache Transcripts/"

        # Iterate over each JSON file in the directory
        for filename in os.listdir(json_directory):
            if filename.endswith(".json"):
                file_path = os.path.join(json_directory, filename)


                print("Creating a new cache with file: ", file_path)

                # Read the content of the JSON file
                with open(file_path, 'rb') as file:
                    file_content = file.read()

                docs.append(file_content)
 
                # # Upload the JSON file using the File API
                # document = client.files.upload(
                #     file=io.BytesIO(file_content),
                #     config=dict(mime_type='application/json')
                # )
                
                # # Print the uploaded document details
                # print(f'Uploaded {filename}: {document}')

                # # save the document into an array for later
                # docs.append(document)

                # # append to the list of files
                # docs.append(file_content)


        # Create a cached content object
        cache = client.caches.create(
                    model=model_name,
                    config=types.CreateCachedContentConfig(
                    system_instruction=system_instruction,
                    contents=docs,
                    )
        )
        cache_name = cache.name

        # Save the cache name to a file
        with open(cache_file, 'w') as f:
            f.write(cache_name)
        print(f"Created new cache file: {cache_name}")

        return cache_name



if __name__ == "__main__":
    create_new_cache()

    

# long_context_pdf_path = "https://www.nasa.gov/wp-content/uploads/static/history/alsj/a17/A17_FlightPlan.pdf"

# # Retrieve and upload the PDF using the File API
# doc_io = io.BytesIO(httpx.get(long_context_pdf_path).content)

# document = client.files.upload(
#   file=doc_io,
#   config=dict(mime_type='application/pdf')
# )

# available_models = client.models.list()
# for model in available_models:
#        print(model)


    # # Generate content using the cached prompt and document
    # response = client.models.generate_content(
    # model=model_name,
    # contents=query,
    # config=types.GenerateContentConfig(
    #         cached_content=get_cache_name()
    #         #cached_content=cache.name
    # ))


    # # (Optional) Print usage metadata for insights into the API call
    # # print(f'{response.usage_metadata=}')

    # # Print the generated text
    # print('\n\n', response.text)