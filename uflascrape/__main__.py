from .sig.client import Sig
import logging
from .model import dump, Disciplina, Curso, load
import json
from .log import *
from datetime import timedelta, date
from itertools import count
from .sql import build_sql

logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())
load(json.load(open('a.json')))

sig = Sig()
# cursos = sig.get_cursos()
cursos = list(Curso._values())
periodos = sig.get_periodos()
discs = list(Disciplina._values())
s = build_sql(cursos, discs, '2023/1 - Campus Sede')
open('c.sql', 'w', encoding='utf-8').write(s)
try:
    raise RuntimeError('no')
    for i, disc in enumerate(discs):
        print(f'{i+1}/{len(discs)} {disc}')
        for periodo in periodos:
            if periodo.key in disc.ofertas:
                print(f'already got {periodo}, skipping')
                continue

            sig.get_disciplina_pub(disc, periodo)
    n_fail = 0
    for i in count():
        d = date.today() - timedelta(days=i)
        print(d.isoformat())
        c = sig.get_cardapio(d)
        print(c)
        if c.almoco is None and c.jantar is None:
            n_fail += 1
            if n_fail > 30:
                break
        else:
            n_fail = 0
finally:
    pass
    # open('a.json', 'w').write(json.dumps(dump(), indent='\t'))
