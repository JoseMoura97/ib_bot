"""
Root wrapper for IB Client Portal / Web API client.

Implementation lives in `system/execution/ib_web_client.py`.
"""

try:
    from system.execution.ib_web_client import IBWebClient as IBWebClient  # type: ignore
except Exception as _e:  # pragma: no cover
    class IBWebClient:  # type: ignore
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "IBWebClient requires the optional dependency `ibind`. "
                "Install it (and any IB Client Portal prerequisites) to use this module."
            ) from _e
