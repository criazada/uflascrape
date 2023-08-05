from pydantic import BaseModel, PlainSerializer, BeforeValidator, Field
from typing import Optional, Annotated, Any
from collections import defaultdict
from pydantic import TypeAdapter
from typing import Generator

_cursos: dict[str, 'Curso'] = {}
class Curso(BaseModel):
    class MatrizCurricular(BaseModel):
        class DisciplinaMatriz(BaseModel):
            disc: 'DisciplinaCell'
            """Disciplina da matriz curricular"""
            percentual: float
            """Percentual mínimo exigido"""
            reqs_fortes: list['DisciplinaCell']
            """Requisitos fortes"""
            reqs_minimos: list['DisciplinaCell']
            """Requisitos mínimos"""
            coreqs: list['DisciplinaCell']
            """Co-requisitos"""

            def disciplinas(self) -> Generator['DisciplinaCell', None, None]:
                yield self.disc
                yield from self.reqs_fortes
                yield from self.reqs_minimos
                yield from self.coreqs

        cod: str
        """Código da matriz curricular"""
        sig_cod_int: int
        """Código interno do SIG"""
        nome: str
        """Nome da matriz curricular"""
        descricao: str
        """Descrição da matriz curricular"""
        periodos: int
        """Número de períodos da matriz curricular"""
        min_periodos: int
        """Número mínimo de períodos para conclusão"""
        max_periodos: int
        """Número máximo de períodos para conclusão"""
        vagas: int
        """Número de vagas semestrais"""
        obrigatorias: dict[int, list[DisciplinaMatriz]] = Field(default_factory=lambda: defaultdict(list))
        """Disciplinas obrigatórias por período"""
        eletivas: dict[str, list[DisciplinaMatriz]] = Field(default_factory=lambda: defaultdict(list))
        """Disciplinas eletivas por categoria"""

        def disciplinas(self) -> Generator['DisciplinaCell', None, None]:
            def _disciplinas(l: list[Curso.MatrizCurricular.DisciplinaMatriz]) -> Generator['DisciplinaCell', None, None]:
                for d in l:
                    yield from d.disciplinas()
            for l in self.obrigatorias.values():
                yield from _disciplinas(l)
            for l in self.eletivas.values():
                yield from _disciplinas(l)

    cod: str
    """Código do curso"""
    sig_cod_int: int
    """Código interno do SIG"""
    nome: str
    """Nome do curso"""
    matrizes: list[MatrizCurricular] = Field(default_factory=list)
    """Matrizes curriculares do curso"""

    def save(self):
        if self.cod in _cursos:
            raise ValueError(f'Curso {self.cod} already registered')
        _cursos[self.cod] = self

    def disciplinas(self) -> Generator['DisciplinaCell', None, None]:
        for matriz in self.matrizes:
            yield from matriz.disciplinas()

    @classmethod
    def get(cls, cod: 'str | Curso') -> Optional['Curso']:
        if isinstance(cod, Curso):
            cod = cod.cod
        return _cursos.get(cod)

    @classmethod
    def load(cls, data: list[Any]):
        for curso in data:
            c = Curso.model_validate(curso)
            _cursos[c.cod] = c

class _CursoCell(BaseModel):
    curso: str | Curso

    @classmethod
    def get(cls, cod: 'str | Curso') -> 'CursoCell':
        if isinstance(cod, Curso):
            cod = cod.cod
        return cls(curso=_cursos[cod])

CursoCell = Annotated[
    _CursoCell,
    PlainSerializer(lambda x: x.curso.cod if isinstance(x.disc, Curso) else x.curso, str),
    BeforeValidator(_CursoCell.get)
]

_professores: dict[str, '_Professor'] = {}
class _Professor(BaseModel):
    nome: str
    """Nome do professor"""

    @classmethod
    def get(cls, nome: str) -> Optional['_Professor']:
        return _professores.get(nome)

    def save(self):
        if self.nome in _professores:
            raise ValueError(f'Professor {self.nome} already registered')
        _professores[self.nome] = self

    @classmethod
    def load(cls, data: list[Any]):
        for professor in data:
            p = cls.model_validate(professor)
            _professores[p.nome] = p

Professor = Annotated[
    _Professor,
    PlainSerializer(lambda x: x.nome, str),
    BeforeValidator(_Professor.get)
]

_locais: dict[str, '_Local'] = {}
class _Local(BaseModel):
    abbr: str
    """Abreviação do local"""
    local: str
    """Nome do local"""
    ocupacao: int
    """Capacidade do local"""

    @classmethod
    def get(cls, abbr: 'str | _Local') -> Optional['_Local']:
        if isinstance(abbr, _Local):
            abbr = abbr.abbr
        return _locais.get(abbr)

    def save(self):
        if self.abbr in _locais:
            raise ValueError(f'Local {self.abbr} already registered')
        _locais[self.abbr] = self

    @classmethod
    def load(cls, data: list[Any]):
        for local in data:
            l = cls.model_validate(local)
            _locais[l.abbr] = l

Local = Annotated[
    _Local,
    PlainSerializer(lambda x: x.abbr, str),
    BeforeValidator(_Local.get)
]

_disciplinas: dict[str, 'Disciplina'] = {}
class Disciplina(BaseModel):
    class Oferta(BaseModel):
        class Vagas(BaseModel):
            oferecidas: int
            """Quantidade de vagas oferecidas"""
            ocupadas: int
            """Quantidade de vagas ocupadas"""
            restantes: int
            """Quantidade de vagas restantes"""
            pendentes: int
            """Quantidade de matrículas pendentes"""

        class HorarioLocal(BaseModel):
            class Horario(BaseModel):
                dia: int
                """Dia da semana (0 - domingo, 1 - segunda, ..., 6 - sábado)"""
                hora: int
                """Hora do dia"""
                minuto: int
                """Minuto da hora"""

            inicio: Horario
            """Horário de início da aula"""
            fim: Horario
            """Horário de fim da aula"""
            local: Local
            """Local da aula"""

        situacao: str
        curso: Curso
        """Curso da oferta"""
        normal: Vagas
        """Vagas normais"""
        especial: Vagas
        """Vagas especiais"""
        horarios: list[HorarioLocal] = Field(default_factory=list)
        """Horários e locais da oferta"""
        semestre: Optional[int] = None
        """Se a oferta é semestral, qual o semestre atual dela"""
        bimestre: Optional[str] = None
        """Se a oferta é bimestral, qual o bimestre atual dela"""

    cod: str
    """Código da disciplina"""
    nome: str
    """Nome da disciplina"""
    creditos: int
    """Quantidade de créditos da disciplina"""
    ofertas: list[Oferta] = Field(default_factory=list)
    """Ofertas da disciplina"""

    @classmethod
    def get(cls, cod: str) -> Optional['Disciplina']:
        return _disciplinas.get(cod)

    @classmethod
    def _get(cls, cod: str) -> 'Disciplina':
        if isinstance(cod, Disciplina):
            cod = cod.cod
        return _disciplinas[cod]

    def save(self):
        if self.cod in _disciplinas:
            raise ValueError(f'Disciplina {self.cod} already registered')
        _disciplinas[self.cod] = self

    @classmethod
    def load(cls, data: list[Any]):
        for disciplina in data:
            d = cls.model_validate(disciplina)
            _disciplinas[d.cod] = d

    def cell(self) -> '_DisciplinaCell':
        return _DisciplinaCell(disc=self)

class _DisciplinaCell(BaseModel):
    disc: str | Disciplina

    @classmethod
    def get(cls, cod: 'str | _DisciplinaCell') -> '_DisciplinaCell':
        if isinstance(cod, _DisciplinaCell):
            return cod
        if cod in _disciplinas:
            return cls(disc=_disciplinas[cod])
        return cls(disc=cod)

DisciplinaCell = Annotated[
    _DisciplinaCell,
    PlainSerializer(lambda x: x.disc.cod if isinstance(x.disc, Disciplina) else x.disc, str),
    BeforeValidator(_DisciplinaCell.get)
]

def load(data: dict[str, Any]):
    Curso.load(data['cursos'])
    Local.load(data['locais'])
    Professor.load(data['professores'])
    Disciplina.load(data['disciplinas'])

def adapt_and_dump(data: Any) -> Any:
    return TypeAdapter(type(data)).dump_python(data)

def dump() -> dict[str, Any]:
    return {
        'cursos': adapt_and_dump(_cursos),
        'locais': adapt_and_dump(_locais),
        'professores': adapt_and_dump(_professores),
        'disciplinas': adapt_and_dump(_disciplinas)
    }

__all__ = [
    "Curso",
    "Local",
    "Professor",
    "Disciplina",
    "load",
    "dump"
]
