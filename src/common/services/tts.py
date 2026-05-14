# # # import asyncio
# # # import edge_tts
# # # import tempfile
# # # import os

# # # async def text_to_speech(
# # #     text: str,
# # #     voice: str = "en-US-JennyNeural",
# # #     rate: str = "+0%",
# # #     pitch: str = "+0Hz",
# # #     volume: str = "+0%",
# # #     save_path: str = None,
# # #     return_bytes: bool = True
# # # ):
# # #     """
# # #     Convert text to speech using edge-tts.

# # #     Parameters:
# # #         text (str): Text to convert
# # #         voice (str): Voice name (e.g., 'en-US-JennyNeural')
# # #         rate (str): Speed ('-50%' to '+100%')
# # #         pitch (str): Pitch ('-50Hz' to '+50Hz')
# # #         volume (str): Volume ('-50%' to '+100%')
# # #         save_path (str): File path to save (optional)
# # #         return_bytes (bool): Return audio bytes

# # #     Returns:
# # #         bytes or file path
# # #     """

# # #     communicate = edge_tts.Communicate(
# # #         text=text,
# # #         voice=voice,
# # #         rate=rate,
# # #         pitch=pitch,
# # #         volume=volume
# # #     )

# # #     # If no path provided → use temp file
# # #     if save_path is None:
# # #         tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
# # #         save_path = tmp_file.name
# # #         tmp_file.close()

# # #     await communicate.save(save_path)

# # #     if return_bytes:
# # #         with open(save_path, "rb") as f:
# # #             audio_bytes = f.read()
# # #         return audio_bytes
# # #     else:
# # #         return save_path


# # # # 🔥 Wrapper to call async function easily
# # # def tts(text, **kwargs):
# # #     return asyncio.run(text_to_speech(text, **kwargs))


# # # # ✅ Example usage
# # # if __name__ == "__main__":
# # #     audio = tts(
# # #         text="Hello! This is a fully customizable text to speech system.",
# # #         voice="en-US-GuyNeural",
# # #         rate="+20%",
# # #         pitch="+10Hz",
# # #         volume="+0%",
# # #         save_path="output.mp3",
# # #         return_bytes=False
# # #     )

# # #     print("Saved to:", audio)


# # # # stream audio------------------------------------------------------------------------------------------------

import pyttsx3
from config.settings import settings
import logging
logger = logging.getLogger(__name__)

def text_to_speech(text, rate=150, volume=1.0, voice_id=None):
    engine = pyttsx3.init()

    # 🔊 Set speech rate (speed)
    engine.setProperty('rate', rate)  # default ~200

    # 🔊 Set volume (0.0 to 1.0)
    engine.setProperty('volume', volume)

    # 🎤 Get available voices
    voices = engine.getProperty('voices')

    # 🎭 Set voice (male/female)
    if voice_id is not None and voice_id < len(voices):
        engine.setProperty('voice', voices[voice_id].id)
    else:
        # default first voice
        engine.setProperty('voice', voices[0].id)

    # 📢 Speak
    engine.say(text)
    engine.runAndWait()


# 🧪 Example usage
if __name__ == "__main__":
    logger.info("Available Voices:")
    
    engine = pyttsx3.init()
    voices = engine.getProperty('voices')
    
    for i, voice in enumerate(voices):
        logger.info(f"{i}: {voice.name}")

    logger.info("\nSpeaking...\n")

    text_to_speech(
        text="Hello! This is a fully customizable text to speech example.",
        rate=180,     # slower speech
        volume=1.0,   # max volume
        voice_id=132    # change index to switch voice
    )


# import asyncio
# import edge_tts
# import pyaudio
# from pydub import AudioSegment
# import io

# async def stream_tts(text):
#     # ✅ SAFE + NATURAL SETTINGS
#     communicate = edge_tts.Communicate(
#         text=text,
#         voice="en-US-JennyNeural",  # very natural voice
#         rate="-10%",                # slightly slower
#         pitch="+1Hz"                # slight pitch boost
#     )

#     player = pyaudio.PyAudio()
#     stream = None

#     async for chunk in communicate.stream():
#         if chunk["type"] == "audio":
#             # 🔄 Decode MP3 → PCM
#             audio = AudioSegment.from_file(
#                 io.BytesIO(chunk["data"]),
#                 format="mp3"
#             )

#             # 🎧 Open stream once
#             if stream is None:
#                 stream = player.open(
#                     format=player.get_format_from_width(audio.sample_width),
#                     channels=audio.channels,
#                     rate=audio.frame_rate,
#                     output=True
#                 )

#             # ▶️ Play audio
#             stream.write(audio.raw_data)

#             # ⚡ Small delay = smoother streaming
#             await asyncio.sleep(0.0)

#     # 🧹 Cleanup
#     if stream:
#         stream.stop_stream()
#         stream.close()

#     player.terminate()


# # ▶️ Run
# if __name__ == "__main__":
#     asyncio.run(
#         stream_tts("Hello! This is a smooth and stable real time streaming text to speech system.")
#     )

# from google import genai
# # import os
# # client = genai.Client(api_key=settings.gemini_api_key)

# # response = client.models.generate_content(
# #     model="gemini-3-flash-001",
# #     contents="Explain how AI works in a few words",
# # )

# # print(response.text)

# from google import genai
# from google.genai import types
# import wave

# # Set up the wave file to save the output:
# def wave_file(filename, pcm, channels=1, rate=24000, sample_width=2):
#    with wave.open(filename, "wb") as wf:
#       wf.setnchannels(channels)
#       wf.setsampwidth(sample_width)
#       wf.setframerate(rate)
#       wf.writeframes(pcm)

# client = genai.Client()

# response = client.models.generate_content(
#    model="gemini-2.5-flash-preview-tts",
#    contents="Say cheerfully: Have a wonderful day!",
#    config=types.GenerateContentConfig(
#       response_modalities=["AUDIO"],
#       speech_config=types.SpeechConfig(
#          voice_config=types.VoiceConfig(
#             prebuilt_voice_config=types.PrebuiltVoiceConfig(
#                voice_name='Kore',
#             )
#          )
#       ),
#    )
# )

# data = response.candidates[0].content.parts[0].inline_data.data

# file_name='out.wav'
# wave_file(file_name, data) # Saves the file to current directory