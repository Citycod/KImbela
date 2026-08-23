import os
import sys
sys.path.insert(0, '/home/uplix/uplix/KImbela')
from dotenv import load_dotenv
load_dotenv()
from groq import Groq
client = Groq(api_key=os.environ.get('GROQ_API_KEY'))
print("Models:", [m.id for m in client.models.list().data])
