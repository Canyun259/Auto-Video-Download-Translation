"""Run the suite and expose tracebacks as GitHub Actions annotations."""
from pathlib import Path
import unittest

root = Path(__file__).resolve().parent
suite = unittest.defaultTestLoader.discover(str(root / 'tests'), pattern='test_*.py', top_level_dir=str(root))
result=unittest.TextTestRunner(verbosity=2).run(suite)
for case,trace in result.failures+result.errors:
    message=(str(case)+'\n'+trace).replace('%','%25').replace('\r','%0D').replace('\n','%0A')
    print('::error::'+message,flush=True)
raise SystemExit(0 if result.wasSuccessful() else 1)
