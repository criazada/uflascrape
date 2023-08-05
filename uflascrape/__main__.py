from .sig.client import Sig
import logging
from .model import dump
import json
from .log import *

logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())

sig = Sig()
sig.get_cursos()

open('a.json', 'w').write(json.dumps(dump(), indent=1))
