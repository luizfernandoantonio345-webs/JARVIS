import requests
import os

# Test script for voice_v2
# Usage: python test_voice_v2.py path/to/your_audio.wav

if len(os.sys.argv) != 2:
    print("Usage: python test_voice_v2.py <audio_file.wav>")
    exit(1)

audio_file = os.sys.argv[1]
url = "http://localhost:8000/voice/command"

with open(audio_file, 'rb') as f:
    files = {'audio': f}
    response = requests.post(url, files=files)

print("Status:", response.status_code)
print("JSON:", response.json())

# Curl alternative:
# curl -X POST -F "audio=@your_audio.wav" http://localhost:8000/voice/command
