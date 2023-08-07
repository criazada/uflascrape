from .model import RefCurso, RefDisciplina, RefPeriodo, _RefLocal, _RefCurso, _RefDisciplina, _RefPeriodo, _RefProfessor
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

CREATE TABLE IF NOT EXISTS OfertasDisciplina (
    id_oferta INT PRIMARY KEY,
    id_curso VARCHAR(8) NOT NULL,
    id_disc VARCHAR(8) NOT NULL,
    professor VARCHAR(255) NOT NULL,
    turma VARCHAR(8) NOT NULL,

    FOREIGN KEY (id_curso) REFERENCES Cursos(id_curso),
    FOREIGN KEY (id_disc) REFERENCES Disciplinas(id_disc)
);

CREATE TABLE IF NOT EXISTS Aulas (
    id_oferta INT NOT NULL,
    local_curto VARCHAR(16) NOT NULL,
    local_completo VARCHAR(255) NOT NULL,
    dia_semana VARCHAR(8) NOT NULL,
    hora_inicio INT NOT NULL,
    hora_fim INT NOT NULL,

    FOREIGN KEY (id_oferta) REFERENCES OfertasDisciplina(id_oferta)
);
'''

def _build_sql_data(cursos: Sequence[RefCurso],
                    disciplinas: Sequence[RefDisciplina],
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
        for per, discs in curso.matrizes[-1].obrigatorias.items():
            for discm in discs:
                p(f"INSERT INTO DisciplinasMatriz VALUES ('{discm.disc}', '{curso.key}', {per}, NULL);")
        for cat, discs in curso.matrizes[-1].eletivas.items():
            for discm in discs:
                p(f"INSERT INTO DisciplinasMatriz VALUES ('{discm.disc}', '{curso.key}', NULL, '{cat}');")

    dias = ['domingo', 'segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado']
    i = 0
    for disc in disciplinas:
        disc = _RefDisciplina.d(disc)
        for oferta in disc.ofertas[periodo.key]:
            prof = _RefProfessor.d(oferta.professor)
            if prof.nome == '()': continue
            i += 1
            p(f"INSERT INTO OfertasDisciplina VALUES ({i}, '{oferta.curso}', '{disc}', '{oferta.professor}', '{oferta.turma}');")
            for aula in oferta.horarios:
                local = _RefLocal.d(aula.local)
                p(f"INSERT INTO Aulas VALUES ({i}, '{local.abbr}', '{local.local}', '{dias[aula.dia]}', {aula.inicio.hora}, {aula.fim.hora});")
    p(f"END TRANSACTION;")
    return sb.getvalue()

def build_sql(cursos: Sequence[RefCurso],
              disciplinas: Sequence[RefDisciplina],
              periodo: RefPeriodo) -> str:
    return _build_sql_schema() + _build_sql_data(cursos, disciplinas, periodo)
