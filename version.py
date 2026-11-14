from pathlib import Path
BASE=Path(__file__).resolve().parent
__version__=(BASE/'VERSION').read_text(encoding='utf-8').strip()
if __name__=='__main__': print(__version__)
