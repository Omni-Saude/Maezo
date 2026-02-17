"""Builder functions for contract rule extraction.

Each builder extracts raw signals from clause text and returns a rule dict.
Output classification logic is delegated to DMN templates — builders are
intentionally thin: extract inputs, pass raw values, let DMN decide.
"""

from .authorization import build_authorization
from .bundling import build_bundling
from .discount import build_discount
from .glosa import build_glosa
from .indicator import build_indicator
from .opme import build_opme
from .penalty import build_penalty
from .pricing import build_pricing
from .routing import build_routing
from .sla import build_sla
from .whitelist import build_whitelist

__all__ = [
    "build_authorization",
    "build_bundling",
    "build_discount",
    "build_glosa",
    "build_indicator",
    "build_opme",
    "build_penalty",
    "build_pricing",
    "build_routing",
    "build_sla",
    "build_whitelist",
]
