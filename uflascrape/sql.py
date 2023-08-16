from .model import RefCurso, RefDisciplina, RefPeriodo, RefProfessor, _RefLocal, _RefCurso, _RefDisciplina, _RefPeriodo, _RefProfessor
from typing import Sequence
from io import StringIO

def _build_sql_schema() -> str:
    return '''
PRAGMA encoding="UTF-8";
CREATE TABLE IF NOT EXISTS Cursos (
    id_curso VARCHAR(8) PRIMARY KEY,
    nome_curso VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS Disciplinas (
    id_disc VARCHAR(8) PRIMARY KEY,
    nome_disc VARCHAR(255) NOT NULL,
    creditos INT NOT NULL
);

CREATE TABLE IF NOT EXISTS DisciplinasMatriz (
    id_disc VARCHAR(8) NOT NULL,
    id_curso VARCHAR(8) NOT NULL,
    periodo INT,
    cat_eletiva VARCHAR(255),

    PRIMARY KEY (id_disc, id_curso),
    FOREIGN KEY (id_disc) REFERENCES Disciplinas(id_disc),
    FOREIGN KEY (id_curso) REFERENCES Cursos(id_curso)
);

CREATE TABLE IF NOT EXISTS Professores (
    id_prof INT PRIMARY KEY,
    nome_prof VARCHAR(255) NOT NULL,
    departamento VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS OfertasDisciplina (
    id_oferta INT PRIMARY KEY,
    id_curso VARCHAR(8) NOT NULL,
    id_disc VARCHAR(8) NOT NULL,
    turma VARCHAR(8) NOT NULL,
    vagas_restantes INT NOT NULL,
    vagas_ocupadas INT NOT NULL,

    FOREIGN KEY (id_curso) REFERENCES Cursos(id_curso),
    FOREIGN KEY (id_disc) REFERENCES Disciplinas(id_disc)
);

CREATE TABLE IF NOT EXISTS Aulas (
    id_oferta INT NOT NULL,
    nome_local VARCHAR(16) NOT NULL,
    dia_semana VARCHAR(8) NOT NULL,
    hora_inicio INT NOT NULL,
    hora_fim INT NOT NULL,

    FOREIGN KEY (id_oferta) REFERENCES OfertasDisciplina(id_oferta)
);

CREATE TABLE IF NOT EXISTS Leciona (
    id_prof INT NOT NULL,
    id_oferta INT NOT NULL,
    eh_principal INT NOT NULL,

    PRIMARY KEY (id_prof, id_oferta),
    FOREIGN KEY (id_prof) REFERENCES Professores(id_prof),
    FOREIGN KEY (id_oferta) REFERENCES OfertasDisciplina(id_oferta)
);
'''

def _build_sql_data(cursos: Sequence[RefCurso],
                    disciplinas: Sequence[RefDisciplina],
                    professores: Sequence[RefProfessor],
                    periodo: RefPeriodo) -> str:
    sb = StringIO()
    def p(*args, **kwargs):
        print(*args, **kwargs, file=sb)

    periodo = _RefPeriodo.d(periodo)
    p(f"BEGIN TRANSACTION;")
    for curso in cursos:
        curso = _RefCurso.d(curso)
        p(f"INSERT INTO Cursos VALUES ('{curso.key}', '{curso.nome}');")

    for disc in disciplinas:
        disc = _RefDisciplina.d(disc)
        p(f"INSERT INTO Disciplinas VALUES ('{disc.key}', '{disc.nome}', {disc.creditos});")

    for curso in cursos:
        curso = _RefCurso.d(curso)
        if not curso.matrizes: continue
        for per, discs in curso.matrizes[-1].obrigatorias.items():
            for discm in discs:
                p(f"INSERT INTO DisciplinasMatriz VALUES ('{discm.disc}', '{curso.key}', {per}, NULL);")
        for cat, discs in curso.matrizes[-1].eletivas.items():
            for discm in discs:
                p(f"INSERT INTO DisciplinasMatriz VALUES ('{discm.disc}', '{curso.key}', NULL, '{cat}');")


    dias = ['domingo', 'segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'N/A']
    prof_ids = {}
    for prof in professores:
        pr = _RefProfessor.r(prof)
        prof_ids[pr.key] = len(prof_ids)
        p(f"INSERT INTO Professores VALUES ({prof_ids[pr.key]}, '{pr}', '{pr.deref.departamento}');")
    i = 0
    for disc in disciplinas:
        disc = _RefDisciplina.d(disc)
        if periodo.key not in disc.ofertas: continue
        for oferta in disc.ofertas[periodo.key]:
            prof = _RefProfessor.r(oferta.professor_principal).key if oferta.professor_principal is not None else ''
            aloc = oferta.professores_alocados + ([prof] if prof else [])
            aloc = set([_RefProfessor.r(p).key for p in aloc])
            i += 1
            restantes = -1 if oferta.normal is None else oferta.normal.restantes
            ocupadas = -1 if oferta.normal is None else oferta.normal.ocupadas
            p(f"INSERT INTO OfertasDisciplina VALUES ({i}, '{oferta.curso}', '{disc}', '{oferta.turma}', {restantes}, {ocupadas});")
            for pr in aloc:
                p(f"INSERT INTO Leciona VALUES ({prof_ids[pr]}, {i}, {1 if pr == prof else 0});")
            for aula in oferta.horarios:
                local = _RefLocal.d(aula.local)
                hora_fim = aula.fim.hora + (1 if aula.fim.minuto > 0 else 0)
                p(f"INSERT INTO Aulas VALUES ({i}, '{local.abbr}', '{dias[aula.dia]}', {aula.inicio.hora}, {hora_fim});")
    p(f"END TRANSACTION;")
    return sb.getvalue()

def build_sql(cursos: Sequence[RefCurso],
              disciplinas: Sequence[RefDisciplina],
              professores: Sequence[RefProfessor],
              periodo: RefPeriodo) -> str:
    return _build_sql_schema() + _build_sql_data(cursos, disciplinas, professores, periodo)
