"""Qwen MT adapter: one subtitle per request, timestamps kept locally."""
import os
import time
import re
from subtitle_rules import clean_chinese

def translate(cues, post=None, sleep=time.sleep, progress=None):
    if post is None:
        import requests
        post = requests.post
    base = os.environ['TRANSLATE_BASE_URL'].rstrip('/')
    if not base.startswith('https://') or '{' in base:
        raise ValueError('请填写百炼控制台提供的完整 HTTPS 接口地址')
    cache = {}
    output = []
    for start, end, original in cues:
        if original not in cache:
            payload = {
                'model': os.environ['TRANSLATE_MODEL'],
                'messages': [{'role': 'user', 'content': original}],
                'translation_options': {'source_lang': 'auto', 'target_lang': 'Chinese'},
            }
            for attempt in range(4):
                response = post(base + '/chat/completions',
                    headers={'Authorization': 'Bearer ' + os.environ['TRANSLATE_API_KEY']},
                    json=payload, timeout=180)
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < 3:
                        sleep(min(30, 2 ** (attempt + 1)))
                        continue
                response.raise_for_status()
                content = response.json()['choices'][0]['message']['content']
                if not isinstance(content, str) or not content.strip():
                    raise ValueError('MT returned an empty translation')
                cleaned = ' '.join(re.sub(r'<[^>]*>|\{[^}]*\}', '', content).split())
                if not cleaned:
                    raise ValueError('MT returned no subtitle text')
                cache[original] = clean_chinese(cleaned)
                break
            # Conservative pacing; 429 responses also trigger bounded retries.
            sleep(1.1)
        output.append((start, end, cache[original]))
        if progress: progress(len(output),len(cues))
    return output
