from .sig.client import Sig
import logging
from .model import dump, Disciplina, Curso
import json
from .log import *

logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())

sig = Sig()
cursos = sig.get_cursos()
for disc in Disciplina._values():
    disc.ofertas = sig.get_ofertas_pub(disc.as_ref(), 231)

open('a.json', 'w').write(json.dumps(dump(), indent=1))
