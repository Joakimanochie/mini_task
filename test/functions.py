import base64
import os
from groq import Groq
from dotenv import load_dotenv
load_dotenv()
api_key = os.getenv('GROQ_API_KEY')

def image_encorder(image_path):
    with open(image_path, 'rb') as f:
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


def analyse_image(original_image, drawn_image):
    if original_image is None or drawn_image is None:
        return 'Please upload images, before clicking on analyse'
    
    original_data, original_type = image_encorder(original_image)
    drawn_data, drawn_type = image_encorder(drawn_image)
    
    prompt = ''' You are an expert art grader, who specialise in grading student drawn Assigments.
    The first image is the ORIGINAL reference image.
    The second image is a DRAWN version by an artist trying to replicate it.

    Compare the two images carefully and provide:
    1. A SCORE out of 10 (how well the drawn image matches the original)
    2. SIMILARITIES: specific elements that matche well
    3. DIFFERENCES: Missing elements from the original image, misrepresentation from the original image

    Format your response exactly like this:
    SCORE: [number]/ 10

    SIMILARITIES:
    - [point 1]
    -[point 2]

    DIFFERENCES
    -[point 1]
    -[point 2]
    '''
    
    client = Groq(api_key= api_key)
    completion = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[{
            'role': 'user',
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
                    'text': prompt
                } 
            ]
        }]
    )
    return completion.choices[0].message.content