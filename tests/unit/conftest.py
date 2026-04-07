"""
Shared fixtures and module-loading helpers for Lambda unit tests.

Design notes
------------
Lambda modules read os.environ and create boto3 resources/clients at *import
time* (module level), so:

  1. Fake AWS credentials and table-name env vars must be set before any
     lambda module is first imported.
  2. Moto intercepts boto3 calls at the HTTP layer, not at resource-creation
     time.  Module-level ``boto3.resource("dynamodb")`` objects created before
     ``mock_aws`` is active will still be intercepted correctly once the mock
     is started — only the actual API calls need to happen inside the mock
     context.

Module-loading strategy
-----------------------
Each feature's crud/router files are named generically (e.g. ``crud.py``).
To avoid Python's module cache returning the wrong module when two features
both have a ``crud.py``, we register every module under a unique alias
``_lambda_{feature}_{stem}`` in ``sys.modules``.  We *also* register it
under the bare stem (e.g. ``note_crud``) the first time it is loaded so that
intra-feature imports (e.g. ``import note_crud`` inside ``folders.py``) work
without a second disk load.
"""

import importlib.util
import os
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Fake AWS credentials — must be set before any boto3 import
# ---------------------------------------------------------------------------
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SECURITY_TOKEN", "testing")
os.environ.setdefault("AWS_SESSION_TOKEN", "testing")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent.parent.parent
LAYER_DIR = REPO_ROOT / "lambda" / "layer" / "python"

# ---------------------------------------------------------------------------
# Reusable test constant
# ---------------------------------------------------------------------------
USER = "u-test-001"


# ---------------------------------------------------------------------------
# Module loader
# ---------------------------------------------------------------------------

def _register(path: Path, name: str):
    """Load *path* as a Python module and register it under *name*."""
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_lambda(feature: str, filename: str):
    """
    Import ``lambda/{feature}/{filename}`` as a named module.

    * Pre-registers ``db`` and ``response`` from the shared layer.
    * Registers the module under ``_lambda_{feature}_{stem}`` to avoid
      cross-feature name collisions.
    * Also registers under the bare stem the first time (for intra-feature
      imports such as ``import note_crud`` inside ``notes/folders.py``).
    * Adds the feature directory to ``sys.path`` as a fallback.
    """
    # Shared layer
    if "db" not in sys.modules:
        _register(LAYER_DIR / "db.py", "db")
    if "response" not in sys.modules:
        _register(LAYER_DIR / "response.py", "response")
    if "utils" not in sys.modules:
        _register(LAYER_DIR / "utils.py", "utils")

    feature_dir = REPO_ROOT / "lambda" / feature
    stem = Path(filename).stem
    alias = f"_lambda_{feature}_{stem}"

    if alias in sys.modules:
        return sys.modules[alias]

    # Pre-add feature dir so intra-feature imports resolve during exec_module
    feature_str = str(feature_dir)
    if feature_str not in sys.path:
        sys.path.insert(0, feature_str)

    spec = importlib.util.spec_from_file_location(alias, str(feature_dir / filename))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod

    # Always update the bare stem before exec so that intra-feature imports
    # (e.g. ``import crud`` inside router.py) resolve to the correct feature's
    # module.  The conditional guard caused cross-feature contamination when
    # tests ran alphabetically: diagrams loaded first and left its crud.py
    # registered as ``crud``, so feeds/router.py imported the wrong module.
    sys.modules[stem] = mod

    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# DynamoDB table creation helpers
# ---------------------------------------------------------------------------

def make_table(ddb, name: str, pk: str, sk: str | None = None):
    keys = [{"AttributeName": pk, "KeyType": "HASH"}]
    attrs = [{"AttributeName": pk, "AttributeType": "S"}]
    if sk:
        keys.append({"AttributeName": sk, "KeyType": "RANGE"})
        attrs.append({"AttributeName": sk, "AttributeType": "S"})
    return ddb.create_table(
        TableName=name,
        KeySchema=keys,
        AttributeDefinitions=attrs,
        BillingMode="PAY_PER_REQUEST",
    )
