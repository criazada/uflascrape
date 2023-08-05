from .sig.client import Sig
import logging
from .model import dump, _disciplinas
import json
from .log import *

logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())

sig = Sig()
cursos = sig.get_cursos()
sig.ensure_disciplinas(cursos)
d = _disciplinas['GCC125']
d.ofertas = sig.get_ofertas(d)

open('a.json', 'w').write(json.dumps(dump(), indent=1))
