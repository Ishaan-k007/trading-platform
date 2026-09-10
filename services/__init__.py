import os
import sys

# services/trading_pb2_grpc.py is protoc-generated and does a bare
# `import trading_pb2` (not a relative import), which only resolves if
# services/ itself is on sys.path. Nothing else in the repo puts it there,
# so anything importing services.* (app.py, the pipeline scripts,
# strategy_runner.py, ...) would otherwise fail with
# "ModuleNotFoundError: No module named 'trading_pb2'". Fixed once here
# since every import of this package runs __init__.py first.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
