from .sig.client import Sig
import logging
from .model import dump
import json
from .log import *

logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())

sig = Sig()
cursos = sig.get_cursos()
sig.ensure_disciplinas(cursos)

open('a.json', 'w').write(json.dumps(dump(), indent=1))
