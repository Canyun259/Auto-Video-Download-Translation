"""Hard formatting rules for Chinese subtitle lines."""
import unicodedata

def clean_chinese(text):
    lines = []
    for line in text.split("\n"):
        line = line.rstrip()
        while line and (unicodedata.category(line[-1]).startswith("P") or line[-1].isspace()):
            line = line[:-1]
        lines.append(line)
    return "\n".join(lines)

def normalize_transcript(data):
    for key in ("chinese", "screen"):
        if key in data:
            data[key] = [[a, b, clean_chinese(text)] for a, b, text in data[key]]
    return data
