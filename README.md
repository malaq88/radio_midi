# Radio MIDI — servidor de streaming local (FastAPI)

Serviço HTTP de **streaming contínuo** de arquivos `.mp3` para vários clientes (por exemplo ESP32) em paralelo. Cada conexão recebe um fluxo `audio/mpeg` em **chunks** (sem carregar o arquivo inteiro na memória).

## Requisitos

- Python **3.11+**
- Pasta com arquivos `.mp3` (veja estrutura abaixo)
- **FFmpeg** no `PATH` (com `libmp3lame`) — apenas para a **rádio live 24/7** opcional (`/radio/live`)

## Instalação

```bash
cd /caminho/para/radio_midi
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Configuração da pasta de música

Por padrão usa a pasta **`music`** na **raiz do projeto** (a pasta que contém `app/`), não o nome de utilizador no caminho.

**`MUSIC_DIR` relativo** (ex.: `music` ou `media/mp3`) é sempre resolvido em relação a essa raiz do repositório, **independentemente** de onde corras o `uvicorn`.

Para uma pasta **fora** do projeto (Docker, NAS, etc.), usa um caminho **absoluto**:

```bash
export MUSIC_DIR=/mnt/nas/musicas
```

Na raiz do projeto podes usar um `.env` (já incluído no exemplo do repo):

```env
MUSIC_DIR=music
```

### Playlists por pasta (bonus)

Arquivos **diretamente** na raiz de `MUSIC_DIR` pertencem ao grupo `root`. Arquivos em subpastas usam o **nome da primeira pasta** como grupo de playlist, por exemplo:

```text
MUSIC_DIR/
  rock/
    faixa1.mp3
  chill/
    faixa2.mp3
  solto.mp3          → grupo "root"
```

O mapeamento dispositivo → playlist está em `app/config.py` (`DEVICE_PLAYLIST_MAP`):

- `esp32_sala` → pasta `rock`
- `esp32_quarto` → pasta `chill`

Se o mapeamento não existir ou a pasta estiver vazia, o endpoint por dispositivo usa **toda a biblioteca** (comportamento igual ao aleatório global).

## Executar o servidor

Na raiz do projeto (onde existe a pasta `app/`):

```bash
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- Documentação interativa: `http://127.0.0.1:8000/docs`
- Saúde: `GET /health`

### Rádio live 24/7 (um único stream, estilo emissora)

O endpoint `GET /radio/live` **não** gera áudio dentro do FastAPI: faz *proxy* para um processo separado que corre **FFmpeg** e um mini-servidor HTTP em `127.0.0.1:9000`.

1. **Terminal 1 — gerador** (deixa a correr; mesmo sem clientes o FFmpeg continua no ar):

   ```bash
   cd /caminho/para/radio_midi
   source .venv/bin/activate
   python3 -m app.services.radio_generator
   ```

2. **Terminal 2 — API** (como habitual):

   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

3. Ouvir a mesma emissão que todos os outros clientes:

   ```bash
   curl -N "http://127.0.0.1:8000/radio/live" -o /dev/null
   ```

Estado do gerador (faixa estimada, clientes, ciclos FFmpeg): `GET /radio/live/status`

Variáveis úteis (`.env` ou ambiente):

| Variável | Efeito |
|----------|--------|
| `RADIO_LIVE_BIND_HOST` | Host do gerador (padrão `127.0.0.1`). |
| `RADIO_LIVE_BIND_PORT` | Porta do gerador (padrão `9000`). |
| `RADIO_LIVE_STREAM_URL` | URL que o FastAPI usa para proxy (padrão `http://127.0.0.1:9000/stream`). |
| `RADIO_LIVE_STATUS_URL` | JSON de estado (padrão `http://127.0.0.1:9000/status`). |
| `RADIO_LIVE_AUTOSTART` | Se `true`, o lifespan do FastAPI arranca `python3 -m app.services.radio_generator` como subprocess (útil em dev; em produção prefira systemd/supervisor). |

## Comandos úteis (raiz do projeto)

Com o **venv ativo** (`source .venv/bin/activate`) e **à partir da pasta que contém `app/`** (a raiz do repositório):

| Objetivo | Comando |
|----------|---------|
| **Servidor** (API + interface web) | `uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| **Rádio live 24/7** (FFmpeg; processo separado do FastAPI) | `python3 -m app.services.radio_generator` |
| **Pasta de música** — criar `MUSIC_DIR`, relatório de `.mp3` por grupo, listar soltos na raiz | `python3 -m music_organize` |
| Garantir só que `MUSIC_DIR` existe | `python3 -m music_organize --init` |
| Mover `.mp3` da raiz de `MUSIC_DIR` para uma subpasta (ex. após copiar/colar) | `python3 -m music_organize --move-loose inbox` (usa `--dry-run` para simular) |
| **Reorganizar** ficheiros já na biblioteca para `{Artista}/{Álbum}/…` (tags ID3) | `python3 scripts/reorganize_music.py` (opção `--music-dir /caminho`) |
| **Saúde** da API | `curl -s http://127.0.0.1:8000/health` |
| **Teste** de stream aleatório | `curl -N -H "Accept: audio/mpeg" "http://127.0.0.1:8000/radio/random" -o /dev/null` |
| **Documentação** interativa (OpenAPI) | Abrir `http://127.0.0.1:8000/docs` no browser |
| **FFmpeg** instalado? (necessário para o gerador live) | `ffmpeg -version` |

O utilitário `music_organize` está em `utils/music_organize/`; o módulo `music_organize` na raiz existe para poder correr `python3 -m music_organize`. Usa as mesmas regras de `MUSIC_DIR` que `app.config` (`.env` ou pasta `music/` por defeito).

### Reorganizar músicas já existentes (Artista / Álbum)

Para mover todos os `.mp3` que já estão em `MUSIC_DIR` para a mesma árvore que os uploads (`{Artista}/{Álbum}/{NN} - {Título}.mp3`), na raiz do projeto:

```bash
source .venv/bin/activate
python3 scripts/reorganize_music.py
```

Outra pasta (ex. `/music` no sistema):

```bash
python3 scripts/reorganize_music.py --music-dir /music
```

Use `--overwrite` para substituir ficheiros/capas no destino. O script usa as mesmas tags ID3 e regras que o upload. Para **só inspecionar** a pasta ou **mover ficheiros soltos** na raiz para uma subpasta manualmente, usa `python3 -m music_organize` (secção **Comandos úteis** acima).

## Endpoints principais

| Método | Caminho | Descrição |
|--------|---------|-----------|
| GET | `/` | Página web (reprodutor HTML5, rádio e lista de músicas) |
| GET | `/radio/live` | **Proxy** do stream único 24/7 (FFmpeg noutro processo); todos ouvem o mesmo sinal; requer gerador a correr |
| GET | `/radio/live/status` | JSON do gerador (faixa estimada, clientes, erros) |
| GET | `/radio/random` | Rádio contínua: shuffle (evita repetir as últimas 5 faixas por ligação), sem fechar a conexão |
| GET | `/radio/device/{device_id}` | Stream por dispositivo (shuffle como acima) |
| GET | `/radio/artist/{artist_name}` | Todas as faixas do artista (1.ª pasta); shuffle contínuo; **404** se não existir |
| GET | `/radio/album/{artist_name}/{album_name}` | Álbum (2.ª pasta); ordem por prefixo `NN` no nome do ficheiro; ciclo contínuo; **404** se não existir |
| GET | `/radio/folder/{folder_name}` | Igual a artista: tudo sob a pasta de topo; shuffle |
| GET | `/radio/file?relative_path=…` | Uma faixa MP3 (ficheiro completo; bom para `<audio>` no browser) |
| GET | `/artists` | Lista JSON de pastas de artista (índice em memória) |
| GET | `/albums/{artist}` | Lista JSON de álbuns desse artista (**404** se artista desconhecido) |
| GET | `/songs` | Lista faixas e resumo de playlists por pasta |
| GET | `/health` | Estado do serviço e quantidade de faixas indexadas |
| POST | `/upload` | Um ficheiro `.mp3` (multipart); requer `UPLOAD_API_KEY` |
| POST | `/upload/zip` | Arquivo `.zip` só com `.mp3`; requer `UPLOAD_API_KEY` |

### Upload (exposto na Internet)

1. **`UPLOAD_API_KEY`** no `.env` (por defeito no repo de desenvolvimento: `radio_midi_dev`). Sem chave (valor vazio), os endpoints respondem **503**. **Em produção** use um segredo longo e aleatório e nunca o valor de teste.
2. Envie o segredo em **`X-API-Key: <token>`** ou **`Authorization: Bearer <token>`**.
3. Limite de um MP3: **20 MB** por defeito (`UPLOAD_MAX_MP3_BYTES`). Ficheiro **.zip**: **512 MB** (`UPLOAD_MAX_ZIP_BYTES`). Total **descomprimido** (soma dos MP3 no ZIP): **2 GB** por defeito (`UPLOAD_MAX_ZIP_UNCOMPRESSED_BYTES`).
4. **`overwrite=true`** (query) substitui o ficheiro de destino e a capa do álbum se já existirem. Com `overwrite=false`, colisões de nome recebem sufixo ` (1)`, ` (2)`, …
5. Após sucesso, a **biblioteca é re-escaneada** automaticamente.

#### Organização automática (ID3)

Após **`POST /upload`** ou **`POST /upload/zip`**, cada MP3 é movido para:

`MUSIC_DIR/{Artista}/{Álbum}/{NN} - {Título}.mp3`

- Metadados via **mutagen** (EasyID3 + frames `TPE1`, `TALB`, `TIT2`, `TRCK`; primeira **APIC** para capa).
- Sem artista → `Unknown Artist`; sem álbum → `Unknown Album`; sem título → nome do ficheiro (ou *hint* do campo opcional `relative_path`).
- Número de faixa `NN` a partir de `TRCK` (ex. `3/12` → `03`); se faltar → `00`.
- Nomes de pastas/ficheiros **sanitizados** (Unicode NFKD, sem caracteres inválidos).
- **Capa**: `cover.jpg` ou `cover.png` na pasta do álbum (se existir imagem embutida).
- O processamento pesado corre em **`asyncio.to_thread`** para não bloquear o event loop.

**Nota:** com esta árvore, o primeiro segmento de cada caminho é o **artista** (não `rock`/`chill`). O mapeamento `DEVICE_PLAYLIST_MAP` usa esse segmento — atualize-o se ainda quiser salas por “género”.

Exemplo `curl` (MP3):

```bash
curl -X POST "http://127.0.0.1:8000/upload?overwrite=false" \
  -H "X-API-Key: o-seu-segredo" \
  -F "file=@/caminho/faixa.mp3" \
  -F "relative_path=hint_titulo_opcional"
```

## Testar com `curl`

```bash
curl -N -H "Accept: audio/mpeg" "http://127.0.0.1:8000/radio/random" --output /dev/null
curl -s "http://127.0.0.1:8000/songs" | jq .
```

## Estabilidade do streaming (buffer, fila, transições)

O fluxo de áudio usa **fila limitada** (`asyncio.Queue`), **agregação** de leituras em blocos maiores antes de enviar ao cliente, e **reutilização do mesmo buffer** entre o fim de uma faixa e o início da seguinte (menos pacotes TCP minúsculos nas junções). A ligação HTTP **não é fechada** entre músicas.

Variáveis de ambiente (ou campos em `Settings` em `app/config.py`):

| Variável | Efeito |
|----------|--------|
| `STREAM_CHUNK_SIZE` | Tamanho de cada `read()` no disco (p.ex. 4096). |
| `STREAM_EMIT_CHUNK_SIZE` | Tamanho mínimo de cada bloco enviado na resposta HTTP (p.ex. 8192); deve ser ≥ ao anterior. |
| `STREAM_QUEUE_MAX_CHUNKS` | Quantos blocos já emitidos podem estar em fila (amortiza picos de disco/rede). |
| `STREAM_TRANSITION_GAP_FILE` | Caminho (absoluto ou relativo à raiz do projeto) a um **MP3 curto de silêncio** entre faixas; opcional, ver `app/assets/README.txt`. |

## Notas para clientes ESP32

- Use **streaming HTTP** (ler o corpo aos poucos), não espere `Content-Length` fixo no rádio contínuo.
- `Cache-Control` está definido para evitar cache agressivo de proxy.
- Se o cliente tiver pouca RAM, reduza `STREAM_EMIT_CHUNK_SIZE` e/ou `STREAM_QUEUE_MAX_CHUNKS`; se a rede for instável, aumente ligeiramente a fila e o tamanho emitido.

## Estrutura do código

```text
app/
  main.py           # FastAPI + lifespan (scan na subida)
  config.py         # MUSIC_DIR, chunk size, mapeamento dispositivo
  deps.py           # Dependências (biblioteca)
  models/           # Song, DTOs de API
  routes/           # radio, songs
  services/         # library (scan), stream (gerador assíncrono), radio_generator (FFmpeg 24/7)
utils/
  music_organize/   # CLI: python3 -m music_organize (atalho: music_organize/ na raiz)
scripts/
  reorganize_music.py
```
