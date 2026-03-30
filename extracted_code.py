import requests
requests.get('http://localhost:11434').content
#!ollama pull qwen3.5:9b
!ollama pull qwen3-vl:2b
from openai import OpenAI 

OLLAMA_BASE_URL = 'http://localhost:11434/v1'

ollama = OpenAI(base_url = OLLAMA_BASE_URL, api_key = 'ollama')
import base64

def image_encorder(image_path):
    with open (image_path, 'rb') as f:
        data = base64.b64encode(f.read()).decode('utf-8')
    ext = image_path.split('.')[-1].lower()
    media_types = {
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'gif': 'image/gif',
        'webp': 'image/webp'
    }
    media_type = media_types.get(ext, 'image/jpeg')
    return data, media_type
from dotenv import load_dotenv
load_dotenv()
from groq import Groq
import os

client = Groq(api_key=os.environ.get('GROQ_API_KEY'))
def analyse_image(original_image, drawn_image):
    if original_image is None or drawn_image is None:
        return 'Please upload images, before clicking on analyse'
    

    original_data, original_type = image_encorder(original_image)
    drawn_data, drawn_type = image_encorder(drawn_image)
    prompt = ''' You are an expert art grader.
    The first image is the ORIGINAL reference image.
    The second image is a DRAWN version by an artist trying to replicate it.

    Compare the two images carefully and provide:
    1. A SCORE out of 10 (how well the drawn image matches the original)
    2. SIMILARITIES: specific elements that matche well

    Format your response exactly like this:
    SCORE: [number]/ 10

    SIMILARITIES:
    - [point 1]
    -[point 2]
    '''
    # response = ollama.chat.completions.create(model = 'qwen3-vl:2b',
    completion = client.chat.completions.create(model="meta-llama/llama-4-scout-17b-16e-instruct",
                            messages = [{
                                'role' : 'user',
                                'content': [
                                    { 
                                        'type': 'image_url',
                                        'image_url': {
                                            'url': f'data:{original_type};base64,{original_data}'
                                        }
                                },
                                  { 
                                        'type': 'image_url',
                                        'image_url': {
                                            'url': f'data:{drawn_type};base64,{drawn_data}'
                                        }
                                },
                                {
                                    'type': 'text',
                                    'text':prompt
                                } 
                                
                                ]
                            }]
        )
    return completion.choices[0].message
original = r"C:\Users\HP\Videos\Github\nitHub\Image\original.jpg"
drawn = r"C:\Users\HP\Videos\Github\nitHub\Image\drawn.jpg"


analyse_image(original, drawn)

completion = client.chat.completions.create(
    model="meta-llama/llama-4-scout-17b-16e-instruct",
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "What's in this image?"
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "https://upload.wikimedia.org/wikipedia/commons/f/f2/LPU-v1-die.jpg"
                    }
                }
            ]
        }
    ],
    temperature=1,
    max_completion_tokens=1024,
    top_p=1,
    stream=False,
    stop=None,
)

print()

