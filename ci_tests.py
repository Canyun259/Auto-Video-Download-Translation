"""Run the suite and expose tracebacks as GitHub Actions annotations."""
import sys,unittest
suite=unittest.defaultTestLoader.discover('.',pattern='test_*.py')
result=unittest.TextTestRunner(verbosity=2).run(suite)
for case,trace in result.failures+result.errors:
    message=(str(case)+'\n'+trace).replace('%','%25').replace('\r','%0D').replace('\n','%0A')
    print('::error::'+message,flush=True)
raise SystemExit(0 if result.wasSuccessful() else 1)
