from .sig.client import Sig
import logging
from .model import dump, Disciplina, Curso, Periodo, load
import json
from .log import *

logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())
load(json.load(open('a.json')))

sig = Sig()
# cursos = sig.get_cursos()
cursos = list(Curso._values())
periodos = sig.get_periodos()
discs = list(Disciplina._values())
try:
    for i, disc in enumerate(discs):
        print(f'{i+1}/{len(discs)} {disc}')
        for periodo in periodos:
            k = periodo._get_key()
            if k in disc.ofertas:
                print(f'already got {periodo}, skipping')
                continue

            sig.get_disciplina_pub(disc.as_ref(), periodo.as_ref())
finally:
    open('a.json', 'w').write(json.dumps(dump(), indent='\t'))
