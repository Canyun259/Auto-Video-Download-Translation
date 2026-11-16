"""Validate uploaded captions and replace an existing review draft safely."""
import copy
import html
import json
import re
import uuid
from pathlib import Path
from review_tools import atomic_json, validate_edit


def read_captions(content, name):
    suffix = Path(name).suffix.lower()
    if suffix not in {'.srt', '.vtt'}:
        raise ValueError('仅支持 SRT 或 VTT 字幕文件')
    if not content or len(content) > 5 * 1024 * 1024:
        raise ValueError('字幕文件不能为空，且不能超过 5 MB')
    if content.startswith((b'\xff\xfe', b'\xfe\xff')):
        encodings = ['utf-16']
    else:
        encodings = ['utf-8-sig', 'gb18030']
    text = None
    for encoding in encodings:
        try:
            text = content.decode(encoding)
            break
        except UnicodeError:
            pass
    if text is None or '\x00' in text:
        raise ValueError('无法读取字幕编码，请另存为 UTF-8 后再试')
    text = text.replace('\r\n', '\n').replace('\r', '\n').strip()
    if suffix == '.vtt':
        lines = text.splitlines()
        if not lines or not re.fullmatch(r'WEBVTT(?:[ \t].*)?', lines[0]):
            raise ValueError('VTT 文件缺少 WEBVTT 文件头')
        text = '\n'.join(lines[1:]).lstrip('\n')
    stamp = r'(?:\d{2,}:)?\d{2}:\d{2}[.,]\d{3}'
    timing = re.compile(rf'({stamp})\s+-->\s+({stamp})(?:[ \t]+.*)?')
    def seconds(value):
        parts = value.replace(',', '.').split(':')
        if len(parts) == 2:
            parts.insert(0, '0')
        hours, minutes, seconds = map(float, parts)
        if minutes >= 60 or seconds >= 60:
            raise ValueError('时间戳中的分和秒必须小于 60')
        return hours * 3600 + minutes * 60 + seconds
    cues = []
    for number, block in enumerate(re.split(r'\n[ \t]*\n', text), 1):
        lines = block.strip().splitlines()
        if not lines:
            continue
        if suffix == '.vtt' and (re.match(r'^NOTE(?:\s|$)', lines[0]) or lines[0] in {'STYLE', 'REGION'}):
            continue
        index = 0 if '-->' in lines[0] else 1
        match = timing.fullmatch(lines[index]) if index < len(lines) else None
        if not match:
            raise ValueError(f'第 {number} 个字幕块：时间轴格式无效，请检查文件')
        body = html.unescape(re.sub(r'<[^>]+>|\{\\[^}]*\}', '', '\n'.join(lines[index+1:]))).strip()
        if not body or '-->' in body:
            raise ValueError(f'第 {number} 个字幕块：正文为空或字幕块之间缺少空行')
        try:
            start, end = map(seconds, match.groups())
        except ValueError as exc:
            raise ValueError(f'第 {number} 个字幕块：{exc}') from exc
        cues.append((start, end, body))
    if not cues:
        raise ValueError('文件中没有可导入的文字字幕')
    return cues


def prepare_subtitles(content, name, mode='chinese', duration=None):
    if mode not in {'chinese', 'bilingual'}:
        raise ValueError('请选择支持的字幕内容类型')
    cues = read_captions(content, name)
    rows = []
    for number, (start, end, body) in enumerate(cues, 1):
        original = ''
        chinese = body
        if mode == 'bilingual':
            lines = [line.strip() for line in body.splitlines() if line.strip()]
            if len(lines) < 2:
                raise ValueError(f'第 {number} 条字幕：双语格式需要首行中文、后续行原文；单语文件请选择中文字幕')
            chinese, original = lines[0], '\n'.join(lines[1:])
        rows.append({'开始': start, '结束': end, '原文': original, '中文': chinese})
    original, chinese = validate_edit(rows, duration)
    return dict(original=original, chinese=chinese, subtitle_display=mode,
                subtitle_source='imported', subtitle_import_name=Path(name).name, language=None, screen=[])


def import_review_subtitles(folder, content, name, mode='chinese', duration=None):
    prepared = prepare_subtitles(content, name, mode, duration)
    path = folder / 'transcript.json'
    previous = json.loads(path.read_text(encoding='utf-8'))
    data = copy.deepcopy(previous)
    data.update({key: value for key, value in prepared.items() if key not in {'screen', 'language'}})
    # Preserve the exact previous draft before replacing it, including its style and screen text.
    backup = folder / ('transcript-before-import-' + uuid.uuid4().hex + '.json')
    backup.write_bytes(path.read_bytes())
    atomic_json(path, data)
    return data
