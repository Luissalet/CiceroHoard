"""Import, probe and embed local audio/video while retaining original media bytes."""
from __future__ import annotations

import io
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit, unquote
import httpx
from pydantic import BaseModel, model_validator
from . import decks
from .errors import CiceroError, Refused
from .hoard_link.ids import new_ulid as new_id
from .hoard_link.atomic import write_bytes_atomic
from .util import sha256_hex, jdump, jload

FORMATS = {'.mp4': 'video/mp4', '.webm': 'video/webm', '.mov': 'video/quicktime',
           '.mp3': 'audio/mpeg', '.wav': 'audio/wav', '.ogg': 'audio/ogg', '.m4a': 'audio/mp4', '.flac': 'audio/flac'}


class ImportArgs(BaseModel):
    deck_id: str
    path: str = ''
    url: str = ''
    filename: str = ''

    @model_validator(mode='after')
    def _location(self):
        if bool(self.path) == bool(self.url):
            raise ValueError('Supply exactly one path or HTTP(S) media URL')
        if self.url and urlsplit(self.url).scheme not in ('http', 'https'):
            raise ValueError('Use an HTTP(S) media URL')
        return self


class GetArgs(BaseModel):
    deck_id: str
    asset_id: Optional[str] = None


def _probe(path):
    executable = shutil.which('ffprobe')
    if not executable:
        raise CiceroError('Install the media probe runtime to import audio/video.')
    result = subprocess.run([executable, '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)],
                            capture_output=True, timeout=60)
    if result.returncode:
        raise CiceroError('The file is not readable audio/video: ' + result.stderr.decode('utf-8', errors='replace')[:300])
    data = json.loads(result.stdout)
    videos = [s for s in data['streams'] if s.get('codec_type') == 'video' and not s.get('disposition', {}).get('attached_pic')]
    audios = [s for s in data['streams'] if s.get('codec_type') == 'audio']
    if not videos and not audios:
        raise CiceroError('This file contains no audio or video stream.')
    video = videos[0] if videos else {}
    return {'kind': 'video' if videos else 'audio', 'duration': float(data['format'].get('duration') or 0),
            'width': int(video.get('width') or 640), 'height': int(video.get('height') or 120),
            'video_codec': video.get('codec_name'), 'audio_codec': audios[0].get('codec_name') if audios else None}


def add(svc, deck_id, data, filename, origin=None):
    decks._deck_row(svc, deck_id)
    ext = Path(filename).suffix.lower()
    if ext not in FORMATS:
        raise CiceroError('Use MP4, WEBM, MOV, MP3, WAV, OGG, M4A or FLAC media.')
    if not data or len(data) > svc.config.max_upload_bytes:
        raise CiceroError('Media is empty or exceeds the configured upload size.')
    with tempfile.TemporaryDirectory(prefix='cicero-media-') as tmp:
        path = Path(tmp) / ('probe' + ext)
        path.write_bytes(data)
        metadata = _probe(path)
        if (metadata['kind'] == 'video') != FORMATS[ext].startswith('video/'):
            # Audio-only MP4/MOV is valid; preserve container MIME, use the detected block type.
            if metadata['kind'] != 'audio':
                raise CiceroError('The media container does not match the filename.')
        poster = None
        if metadata['kind'] == 'video' and shutil.which('ffmpeg'):
            poster_path = Path(tmp) / 'poster.jpg'
            result = subprocess.run([shutil.which('ffmpeg'), '-v', 'error', '-i', str(path), '-frames:v', '1', '-vf', 'scale=1280:-2', str(poster_path)],
                                    capture_output=True, timeout=60)
            if result.returncode == 0 and poster_path.is_file():
                poster = poster_path.read_bytes()
    digest = sha256_hex(data)
    with svc.db.transaction():
        existing = svc.db.one('SELECT id FROM assets WHERE deck_id=? AND sha256=? AND ext=?', (deck_id, digest, ext[1:]))
        if existing and decks.asset_info(svc, existing['id']):
            return {**inspect(svc, GetArgs(deck_id=deck_id, asset_id=existing['id']))['items'][0], 'reused': True}
        asset_id = new_id()
        svc.config.assets_dir.mkdir(parents=True, exist_ok=True)
        write_bytes_atomic(svc.config.assets_dir / (asset_id + ext), data, fsync=False)
        svc.db.execute('INSERT INTO assets(id,deck_id,filename,mime,ext,width,height,bytes,sha256,created_ts) VALUES(?,?,?,?,?,?,?,?,?,?)',
                       (asset_id, deck_id, filename[:200], FORMATS[ext], ext[1:], metadata['width'], metadata['height'], len(data), digest, svc.clock()))
        metadata['origin'] = origin or {'filename': filename}
        if poster:
            metadata['poster_id'] = decks.add_asset(svc, deck_id, poster, 'media-poster.jpg')['asset_id']
        svc.db.execute('INSERT INTO media_metadata(asset_id,definition) VALUES(?,?)', (asset_id, jdump(metadata)))
    return inspect(svc, GetArgs(deck_id=deck_id, asset_id=asset_id))['items'][0]


def import_media(svc, args):
    if args.path:
        path = Path(args.path).expanduser().resolve()
        if svc.config.file_roots and not any(path.is_relative_to(r.resolve()) for r in svc.config.file_roots):
            raise Refused('Media is outside the configured source folders.')
        if not path.is_file():
            raise CiceroError('The media file does not exist.')
        if path.stat().st_size > svc.config.max_upload_bytes:
            raise CiceroError('Media exceeds the configured upload size.')
        return add(svc, args.deck_id, path.read_bytes(), path.name, {'path': str(path)})
    filename = args.filename or Path(unquote(urlsplit(args.url).path)).name
    try:
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            with client.stream('GET', args.url) as response:
                response.raise_for_status()
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > svc.config.max_upload_bytes:
                        raise CiceroError('Media exceeds the configured upload size.')
    except httpx.HTTPError as error:
        raise CiceroError('Media URL could not be read: ' + str(error)) from error
    return add(svc, args.deck_id, bytes(data), filename, {'url': args.url})


def inspect(svc, args):
    decks._deck_row(svc, args.deck_id)
    rows = svc.db.query('SELECT a.*,m.definition FROM assets a JOIN media_metadata m ON m.asset_id=a.id WHERE a.deck_id=?', (args.deck_id,))
    items = [{'asset_id': r['id'], 'filename': r['filename'], 'mime': r['mime'], 'bytes': r['bytes'],
              'url': '/api/assets/' + r['id'], **jload(r['definition'], {})} for r in rows if not args.asset_id or args.asset_id == r['id']]
    if args.asset_id and not items:
        raise CiceroError('This media asset does not belong to the deck.')
    return {'items': items}


def add_native(slide, box, assets):
    from pptx.oxml.ns import qn
    from pptx.util import Emu
    data = box.data
    info = assets(data['asset_id'])
    poster = assets(data.get('poster_id', ''))
    with tempfile.TemporaryDirectory(prefix='cicero-export-media-') as tmp:
        path = info['path']
        mime = info['mime']
        # Bake trim/rate and unsupported containers into a compatibility copy; never alter the asset.
        convert = data.get('start', 0) > 0 or data.get('end') is not None or data.get('playback_rate', 1) != 1 or path.suffix not in ('.mp4', '.mp3', '.wav') or bool(data.get('subtitles'))
        if convert:
            executable = shutil.which('ffmpeg')
            if not executable:
                raise CiceroError('The media conversion runtime is required for trimming or this container.')
            audio = data['type'] == 'audio'
            output = Path(tmp) / ('clip.mp3' if audio else 'clip.mp4')
            cmd = [executable, '-v', 'error', '-ss', str(data.get('start', 0))]
            if data.get('end') is not None:
                cmd += ['-t', str(data['end'] - data.get('start', 0))]
            cmd += ['-i', str(path)]
            rate = data.get('playback_rate', 1)
            filters = []
            if data.get('subtitles') and not audio:
                (Path(tmp)/'captions.vtt').write_text(data['subtitles'],encoding='utf-8')
                filters = [f"setpts=PTS+{data.get('start',0)}/TB",'subtitles=captions.vtt','setpts=PTS-STARTPTS']
            if rate != 1:
                tempo = []
                remaining = rate
                while remaining > 2:
                    tempo.append('atempo=2'); remaining /= 2
                while remaining < .5:
                    tempo.append('atempo=0.5'); remaining /= .5
                tempo.append('atempo=' + str(remaining))
                if not audio:
                    filters.append(f'setpts=(PTS-STARTPTS)/{rate}')
                # An absent audio stream makes -af harmless; -an below handles silent video.
                if audio or info.get('metadata', {}).get('audio_codec'):
                    cmd += ['-af', ','.join(tempo)]
            if not audio:
                if filters:
                    cmd += ['-vf', ','.join(filters)]
                cmd += ['-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart']
            if data.get('end') is not None:
                cmd += ['-t', str((data['end'] - data.get('start', 0)) / rate)]
            cmd += [str(output)]
            result = subprocess.run(cmd, capture_output=True, timeout=300,cwd=tmp)
            if result.returncode:
                raise CiceroError('Media conversion failed: ' + result.stderr.decode('utf-8', errors='replace')[:300])
            path = output
            mime = 'audio/mpeg' if audio else 'video/mp4'
        shape = slide.shapes.add_movie(str(path), *(Emu(round(v * 9525)) for v in (box.x, box.y, box.w, box.h)),
                                       poster_frame_image=str(poster['path']) if poster else None, mime_type=mime)
    if data['type'] == 'audio':
        for el in shape._element.iter(qn('a:videoFile')):
            el.tag = qn('a:audioFile')
    timing = slide._element.find(qn('p:timing'))
    if timing is not None:
        for node in timing.iter(qn('p:video')):
            target = node.find('.//' + qn('p:spTgt'))
            if target is None or target.get('spid') != str(shape.shape_id):
                continue
            if data['type'] == 'audio':
                node.tag = qn('p:audio')
            media_node = node.find(qn('p:cMediaNode'))
            media_node.set('vol', str(round((0 if data.get('muted') else data.get('volume', 1)) * 100000)))
            media_node.set('showWhenStopped', '1')
            ctn = media_node.find(qn('p:cTn'))
            if data.get('loop'):
                ctn.set('repeatCount', 'indefinite')
            if data.get('autoplay'):
                for cond in ctn.iter(qn('p:cond')):
                    cond.set('delay', '0')
    shape.name = 'Media'
    return shape
