# import edge_tts

# # 🔊 reusable function
# async def generate_audio_stream(text: str, voice: str = "en-US-AriaNeural"):
#     communicate = edge_tts.Communicate(text=text, voice=voice)

#     async for chunk in communicate.stream():
#         if chunk["type"] == "audio":
#             yield chunk["data"]

import edge_tts

async def generate_audio_stream(
    text: str,
    voice: str = "en-US-AriaNeural",
    rate: str = "+0%"   # 👈 add this
):
    communicate = edge_tts.Communicate(
        text=text,
        voice=voice,
        rate=rate       # 👈 apply speed
    )

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            yield chunk["data"]