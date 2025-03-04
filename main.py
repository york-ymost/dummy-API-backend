import os

import uvicorn
import json
import asyncio
import websockets
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket
from openai import OpenAI
from pydub import AudioSegment
import io
import numpy as np
from starlette.websockets import WebSocketDisconnect

load_dotenv()
app = FastAPI()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# OpenAI Whisper Client
client = OpenAI(api_key=OPENAI_API_KEY)

print(f"Loaded OpenAI API Key: {OPENAI_API_KEY[:5]}... (truncated)")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("Client connected")
    audio_chunks = []

    try:
        while True:
            audio_data = await websocket.receive_bytes()
            if not audio_data:
                break  # Handle empty data
            print(f"received chunk size: {len(audio_data)} bytes")
            print(f"First 20 bytes of chunk: {audio_data[:20].hex()}")
            audio_chunks.append(audio_data)

            if sum(len(chunk) for chunk in audio_chunks) >= 48000 * 2 * 1:  # At least 3s of 16-bit PCM audio
                print('about to transcript')
                transcript = await process_audio(audio_chunks)
                await websocket.send_text(json.dumps({"text": transcript}))
                audio_chunks = []  # Reset chunk buffer


    except WebSocketDisconnect:
        print("WebSocket disconnected")

    except Exception as e:
        print(f"WebSocket Error: {e}")

    finally:
        try:
            await websocket.close()
        except RuntimeError:
            print("WebSocket already closed")

async def process_audio(audio_chunks):
    try:
        # Combine all received audio chunks
        audio = b"".join(audio_chunks)

        # Debug: Save the raw received file
        with open("received_audio.webm", "wb") as f:
            f.write(audio)

        print("Saved received_audio_debug.webm for inspection.")

        if not audio.startswith(b'\x1A\x45\xDF\xA3'):
            print("Invalid WebM file header!")
            return "Error: Invalid WebM file format."

        try:
            audio_segment = AudioSegment.from_file(io.BytesIO(audio), format="webm")
            print("WebM audio successfully loaded!")
        except Exception as e:
            print(f"Error loading WebM audio: {e}")
            return "Error loading audio"

        fname = "file.wav"
        # Ensure it's converted to 16-bit PCM WAV (OpenAI Whisper requirement)
        wav_buffer = io.BytesIO()
        wav_buffer.name = fname

        audio_segment = audio_segment.set_frame_rate(16000).set_channels(1).set_sample_width(2)  # 16-bit PCM, mono
        audio_segment.export(wav_buffer, format="wav")

        # Debug: Save the properly formatted WAV file
        with open("final_audio.wav", "wb") as f:
            f.write(wav_buffer.getvalue())

        # wav_buffer.seek(0)
        print(type(wav_buffer))
        # Send correctly formatted WAV file to OpenAI Whisper
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=wav_buffer
        )
        print(response.text)
        return response.text

    except Exception as e:
        print(f"Audio Processing Error: {e}")
        return "Error processing audio"


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
