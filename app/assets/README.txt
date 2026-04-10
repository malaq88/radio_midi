Opcional: coloque aqui um MP3 muito curto de silêncio (ex.: 50–200 ms, mesmo sample rate que a sua música)
e defina no .env: STREAM_TRANSITION_GAP_FILE=app/assets/seu_silencio.mp3
para suavizar a junção entre faixas nos decoders. Gere com: ffmpeg -f lavfi -i anullsrc=r=44100:cl=stereo -t 0.08 -c:a libmp3lame -b:a 192k seu_silencio.mp3
