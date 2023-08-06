from pydantic import BaseModel, Field, model_serializer, model_validator, field_validator, RootModel
from typing import Optional, Any, Generic, Generator, TypeVar, TypeAlias, cast, Self, Iterable, Annotated, ClassVar
from collections import defaultdict

from .log import *
import abc

_refs = defaultdict(dict)

class Resolve(abc.ABC):
    @abc.abstractmethod
    def resolve_refs(self): ...

T = TypeVar('T')
V = TypeVar('V', bound='Ref')
class RefBy(BaseModel, abc.ABC, Generic[T, V]):
    _key: Optional[T] = None
    _key_type: ClassVar[type]

    @abc.abstractmethod
    def _get_key(self) -> T: ...

    @classmethod
    @abc.abstractmethod
    def _get_ref_type(cls) -> 'type[Ref]': ...

    def __new__(cls, **data: Any) -> Self:
        inst = super().__new__(cls)
        inst.__init__(_init=True, **data)
        k = inst._get_key()

        if k not in _refs[cls]:
            _refs[cls][k] = inst
        return _refs[cls][k]

    def __init__(self, **data: Any):
        if '_init' not in data: return

        super().__init__(**data)
        self._key = self._get_key()
        self._init = True

    def _register(self) -> Self:
        cls = self.__class__
        if self._key not in _refs[cls]:
            _refs[cls][self._key] = self
        return _refs[cls][self._key]

    @classmethod
    def ref(cls, key: T) -> V:
        return cast(V, cls._get_ref_type()(key))

    @classmethod
    def _values(cls) -> Iterable[Self]:
        return _refs[cls].values()

    def as_ref(self) -> V:
        return cast(V, self.__class__._get_ref_type()(self))

U = TypeVar('U', bound=RefBy)
class Ref(RootModel[T | U], Generic[T, U]):
    # T is a type that can be used as a key for U
    # U is a type that inherits from RefBy[T]
    root: T | U
    _ref_type: ClassVar[type[RefBy]]

    @model_serializer
    def _serialize(self) -> T:
        cls = self.__class__
        if isinstance(self.root, cls._ref_type):
            assert self.root._key is not None
            return self.root._key
        else:
            assert isinstance(self.root, cls._ref_type._key_type)
            return cast(T, self.root)

    def __init__(self, v: T | U, **data: Any):
        cls = self.__class__
        if isinstance(v, cls._ref_type):
            v = cast(U, v)
        elif isinstance(v, cls._ref_type._key_type):
            v = cast(T, v)
        else:
            raise TypeError(f'Invalid type {type(v)} for root (must be {cls._ref_type} or {cls._ref_type._key_type})')
        super().__init__(v, **data)

    def resolve(self) -> bool:
        cls = self.__class__
        if isinstance(self.root, cls._ref_type): return True
        r = _refs[self._ref_type].get(self.root)
        if r is not None:
            self.root = r
            return True
        else:
            return False

    @property
    def deref(self) -> U:
        if self.resolve():
            return cast(U, self.root)
        raise TypeError(f'Cannot deref {self.root} of type {self.__class__._ref_type}')

    @property
    def key(self) -> T:
        if isinstance(self.root, RefBy):
            assert self.root._key is not None
            return cast(T, self.root._key)
        return self.root

    def __str__(self) -> str:
        return self.root.__str__()

class Curso(RefBy[str, 'RefCurso'], Resolve):
    _key_type = str

    class MatrizCurricular(BaseModel, Resolve):
        class DisciplinaMatriz(BaseModel, Resolve):
            disc: 'RefDisciplina'
            """Disciplina da matriz curricular"""
            percentual: float
            """Percentual mínimo exigido"""
            reqs_fortes: list['RefDisciplina']
            """Requisitos fortes"""
            reqs_minimos: list['RefDisciplina']
            """Requisitos mínimos"""
            coreqs: list['RefDisciplina']
            """Co-requisitos"""

            def disciplinas(self) -> Generator['RefDisciplina', None, None]:
                yield self.disc
                yield from self.reqs_fortes
                yield from self.reqs_minimos
                yield from self.coreqs

            def resolve_refs(self) -> bool:
                for d in self.disciplinas():
                    if not d.resolve(): return False
                return True

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

        def disciplinas(self) -> Generator['RefDisciplina', None, None]:
            def _disciplinas(l: list[Curso.MatrizCurricular.DisciplinaMatriz]) -> Generator['RefDisciplina', None, None]:
                for d in l:
                    yield from d.disciplinas()
            for l in self.obrigatorias.values():
                yield from _disciplinas(l)
            for l in self.eletivas.values():
                yield from _disciplinas(l)

        def resolve_refs(self) -> bool:
            for d in self.disciplinas():
                if not d.resolve(): return False
            return True

    cod: str
    """Código do curso"""
    sig_cod_int: int
    """Código interno do SIG"""
    nome: str
    """Nome do curso"""
    matrizes: list[MatrizCurricular] = Field(default_factory=list)
    """Matrizes curriculares do curso"""

    def resolve_refs(self) -> bool:
        for m in self.matrizes:
            if not m.resolve_refs(): return False
        return True

    def _get_key(self) -> str:
        return self.cod

    def disciplinas(self) -> Generator['RefDisciplina', None, None]:
        for m in self.matrizes:
            yield from m.disciplinas()

    def __str__(self) -> str:
        return f'{self.cod} - {self.nome}'

    @classmethod
    def _get_ref_type(cls) -> type[Ref]:
        return RefCurso

class Professor(RefBy[str, 'RefProfessor']):
    _key_type = str

    nome: str
    """Nome do professor"""

    def _get_key(self) -> str:
        return self.nome

    def __str__(self) -> str:
        return self.nome

    @classmethod
    def _get_ref_type(cls) -> type[Ref]:
        return RefProfessor

class Local(RefBy[str, 'RefLocal']):
    _key_type = str

    abbr: str
    """Abreviação do local"""
    local: str
    """Nome do local"""
    ocupacao: int
    """Capacidade do local"""

    def _get_key(self) -> str:
        return self.abbr

    def __str__(self) -> str:
        return f'{self.abbr} - {self.local}'

    @classmethod
    def _get_ref_type(cls) -> type[Ref]:
        return RefLocal

class Periodo(RefBy[str, 'RefPeriodo']):
    _key_type = str

    nome: str
    """Nome do período"""
    sig_cod_int: str
    """Código interno do SIG"""

    @property
    def nome_short(self) -> str:
        return self.nome.split(' - ')[0]

    def _get_key(self) -> str:
        return self.nome

    def __str__(self) -> str:
        return self.nome

    @classmethod
    def _get_ref_type(cls) -> type[Ref]:
        return RefPeriodo

class Disciplina(RefBy[str, 'RefDisciplina'], Resolve):
    _key_type = str

    class OfertaParcial(BaseModel, Resolve):
        disc: 'RefDisciplina'
        turma: str
        sig_cod_int: int

        def resolve_refs(self):
            return self.disc.resolve()

    class Oferta(BaseModel, Resolve):
        class Vagas(BaseModel):
            oferecidas: int
            """Quantidade de vagas oferecidas"""
            ocupadas: int
            """Quantidade de vagas ocupadas"""
            restantes: int
            """Quantidade de vagas restantes"""
            pendentes: int
            """Quantidade de matrículas pendentes"""

        class HorarioLocal(BaseModel, Resolve):
            class Horario(BaseModel):
                hora: int
                """Hora do dia"""
                minuto: int
                """Minuto da hora"""

                @classmethod
                def from_hora(cls, hora: str) -> Self:
                    h, m = hora.split(':')
                    return cls(hora=int(h), minuto=int(m))

            dia: int
            """Dia da semana (0 - domingo, 1 - segunda, ..., 6 - sábado)"""
            inicio: Horario
            """Horário de início da aula"""
            fim: Horario
            """Horário de fim da aula"""
            local: 'RefLocal'
            """Local da aula"""

            def resolve_refs(self) -> bool:
                return self.local.resolve()

        situacao: str
        turma: str
        curso: 'RefCurso'
        professor: 'RefProfessor'

        """Curso da oferta"""
        normal: Optional[Vagas] = None
        """Vagas normais"""
        especial: Optional[Vagas] = None
        """Vagas especiais"""
        horarios: list[HorarioLocal] = Field(default_factory=list)
        """Horários e locais da oferta"""
        semestre: Optional[int] = None
        """Se a oferta é semestral, qual o semestre atual dela"""
        bimestre: Optional[str] = None
        """Se a oferta é bimestral, qual o bimestre atual dela"""

        def resolve_refs(self) -> bool:
            if not self.curso.resolve(): return False
            if not self.professor.resolve(): return False
            return True

    cod: str
    """Código da disciplina"""
    nome: str
    """Nome da disciplina"""
    creditos: int
    """Quantidade de créditos da disciplina"""
    ofertas: dict[str, list[Oferta]]
    """Ofertas da disciplina por período"""

    def resolve_refs(self) -> bool:
        for os in self.ofertas.values():
            if any(not o.resolve_refs() for o in os): return False
        return True

    def _get_key(self) -> str:
        return self.cod

    def __str__(self) -> str:
        return f'{self.cod} - {self.nome}'

    @classmethod
    def _get_ref_type(cls) -> type[Ref]:
        return RefDisciplina

def load(data: dict[str, Any]):
    for curso in data['cursos']:
        Curso(**curso)
    for local in data['locais']:
        Local(**local)
    for professor in data['professores']:
        Professor(**professor)
    for disciplina in data['disciplinas']:
        Disciplina(**disciplina)
    for periodo in data['periodos']:
        Periodo(**periodo)

def _dump(data: Iterable[BaseModel]) -> Any:
    return [d.model_dump() for d in data]

def dump() -> dict[str, Any]:
    return {
        'cursos': _dump(Curso._values()),
        'locais': _dump(Local._values()),
        'professores': _dump(Professor._values()),
        'disciplinas': _dump(Disciplina._values()),
        'periodos': _dump(Periodo._values())
    }

class RefDisciplina(Ref[str, 'Disciplina']):
    _ref_type = Disciplina

class RefCurso(Ref[str, 'Curso']):
    _ref_type = Curso

class RefLocal(Ref[str, 'Local']):
    _ref_type = Local

class RefProfessor(Ref[str, 'Professor']):
    _ref_type = Professor

class RefPeriodo(Ref[str, 'Periodo']):
    _ref_type = Periodo

__all__ = [
    "Curso",
    "Local",
    "Professor",
    "Disciplina",
    "load",
    "dump"
]
