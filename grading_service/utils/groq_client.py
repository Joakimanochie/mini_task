import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

_client = None


def get_groq_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    return _client
