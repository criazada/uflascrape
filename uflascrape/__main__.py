from .sig.client import Sig
import logging
from .model import dump, Disciplina, Curso, load, Professor, _RefDisciplina
import json
from .log import *
from datetime import timedelta, date
from itertools import count
from .sql import build_sql
import dotenv
import os

dotenv.load()

logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())
load(json.load(open('g.json')))
Curso(cod='G030', sig_cod_int=0, nome='ABI Engenharia')
Curso(cod='G043', sig_cod_int=0, nome='ABI Educação Física')
Curso(cod='G055', sig_cod_int=0, nome='ABI Letras')
sig = Sig()
# cursos = sig.get_cursos()
# periodos = sig.get_periodos()


try:
    raise RuntimeError('no')
    sig.login(os.getenv('USER'), os.getenv('PASSWORD'))
    ofertas = sig.list_ofertas()

    periodo = '2023/2 - Campus Sede'
    discis = {}
    for i, parcial in enumerate(ofertas):
        print(f'{i+1}/{len(ofertas)} {parcial}')
        k = _RefDisciplina.r(parcial.disc).key
        if k not in discis:
            discis[k] = sig.get_disciplina_pub(parcial.disc, periodo)
        oferta = sig.get_oferta(parcial)
        for of in discis[k].ofertas[periodo]:
            if of.turma == oferta.turma:
                of.horarios = oferta.horarios
                of.normal = oferta.normal
                of.especial = oferta.especial
                break

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
    cursos = list(Curso._values())
    discs = list(Disciplina._values())
    profs = list(Professor._values())
    s = build_sql(cursos, discs, profs, '2023/2 - Campus Sede')
    open('d.sql', 'w', encoding='utf-8').write(s)
    # open('g.json', 'w').write(json.dumps(dump(), indent='\t'))
