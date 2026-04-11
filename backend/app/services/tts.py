from pathlib import Path

import edge_tts


class TTSService:
    async def synthesize(self, text: str, voice: str = "en-US-GuyNeural") -> bytes:
        communicate = edge_tts.Communicate(text=text, voice=voice)
        chunks: list[bytes] = []

        async for chunk in communicate.stream():
            if chunk.get("type") != "audio":
                continue
            data = chunk.get("data", b"")
            if isinstance(data, bytes):
                chunks.append(data)
            elif isinstance(data, bytearray):
                chunks.append(bytes(data))

        return b"".join(chunks)

    async def synthesize_to_file(
        self,
        text: str,
        output_path: str,
        voice: str = "en-US-GuyNeural",
    ) -> str:
        audio = await self.synthesize(text=text, voice=voice)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(audio)
        return str(path)
