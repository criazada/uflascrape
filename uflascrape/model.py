from pydantic import BaseModel, Field, model_serializer, field_serializer, RootModel, BeforeValidator
from typing import Optional, Any, Generic, Generator, TypeVar, cast, Self, Iterable, Annotated, ClassVar
from collections import defaultdict
from datetime import date

from .log import *
import abc

_refs = defaultdict(dict)

K = TypeVar('K')
class RefBy(BaseModel, abc.ABC, Generic[K]):
    _key_type: ClassVar[type]

    @abc.abstractmethod
    def _merge(self, other: Self) -> None: ...

    @abc.abstractmethod
    def _get_key(self) -> K: ...

    @property
    def key(self) -> K:
        return self._get_key()

    def __new__(cls, **data: Any) -> Self:
        inst = super().__new__(cls)
        inst.__init__(_init=True, **data)
        k = inst.key

        if k not in _refs[cls]:
            _refs[cls][k] = inst
        _refs[cls][k]._merge(inst)
        return _refs[cls][k]

    def __init__(self, **data: Any):
        if '_init' not in data: return

        super().__init__(**data)
        self._init = True

    @classmethod
    def _values(cls) -> Iterable[Self]:
        return _refs[cls].values()

    @classmethod
    def _get(cls, k: K) -> Optional[Self]:
        return _refs[cls].get(k)

RefByK = TypeVar('RefByK', bound=RefBy)
class Ref(RootModel[K | RefByK], Generic[K, RefByK]):
    # T is a type that can be used as a key for U
    # U is a type that inherits from RefBy[T]
    root: K | RefByK
    _ref_type: ClassVar[type[RefBy]]

    @model_serializer
    def _serialize(self) -> K:
        cls = self.__class__
        if isinstance(self.root, cls._ref_type):
            return self.root.key
        else:
            assert isinstance(self.root, cls._ref_type._key_type)
            return cast(K, self.root)

    @classmethod
    def r(cls, v: K | RefByK | Self) -> Self:
        if isinstance(v, cls): return v
        return cls(v)

    @classmethod
    def d(cls, v: K | RefByK | Self) -> RefByK:
        return cls.r(v).deref

    def __init__(self, v: K | RefByK, **data: Any):
        cls = self.__class__
        if not isinstance(v, (cls._ref_type, cls._ref_type._key_type)):
            raise TypeError(f'Invalid type {type(v)} for root (must be {cls._ref_type} or {cls._ref_type._key_type})')
        super().__init__(v, **data)

    def resolve(self) -> bool:
        cls = self.__class__
        if isinstance(self.root, cls._ref_type): return True
        r = self._ref_type._get(self.root)
        if r is not None:
            self.root = cast(RefByK, r)
            return True
        else:
            return False

    @property
    def deref(self) -> RefByK:
        if self.resolve():
            return cast(RefByK, self.root)
        raise TypeError(f'Cannot deref {self.root} of type {self.__class__._ref_type}')

    @property
    def key(self) -> K:
        cls = self.__class__
        if isinstance(self.root, cls._ref_type):
            return cast(K, self.root._get_key())
        else:
            return cast(K, self.root)

    def __str__(self) -> str:
        return self.root.__str__()

class Curso(RefBy[str]):
    _key_type = str

    class MatrizCurricular(BaseModel):
        class DisciplinaMatriz(BaseModel):
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

    cod: str
    """Código do curso"""
    sig_cod_int: int
    """Código interno do SIG"""
    nome: str
    """Nome do curso"""
    matrizes: list[MatrizCurricular] = Field(default_factory=list)
    """Matrizes curriculares do curso"""

    def _get_key(self) -> str:
        return self.cod

    def disciplinas(self) -> Generator['RefDisciplina', None, None]:
        for m in self.matrizes:
            yield from m.disciplinas()

    def __str__(self) -> str:
        return self.cod
    
    def _merge(self, other: Self): ...

class Professor(RefBy[str]):
    _key_type = str

    nome: str
    """Nome do professor"""
    departamento: str

    def _get_key(self) -> str:
        return self.nome

    def __str__(self) -> str:
        return self.nome
    
    def _merge(self, other: Self):
        if self.departamento == '':
            self.departamento = other.departamento

    @classmethod
    def from_full(cls, full: str) -> Self:
        nome, _, departamento = full.partition(' (')
        return cls(nome=nome, departamento=departamento[:-1])

class Local(RefBy[str]):
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
        return self.abbr
    
    def _merge(self, other: Self): ...

class Periodo(RefBy[str]):
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
    
    def _merge(self, other: Self): ...

class Disciplina(RefBy[str]):
    _key_type = str

    class OfertaParcial(BaseModel):
        disc: 'RefDisciplina'
        turma: str
        sig_cod_int: int

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
                hora: int
                """Hora do dia"""
                minuto: int
                """Minuto da hora"""

                @classmethod
                def from_hora(cls, hora: str) -> Self:
                    if hora == '': return cls(hora=-1, minuto=-1)
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

        situacao: str
        turma: str
        curso: 'RefCurso'
        professor_principal: Optional['RefProfessor'] = None
        professores_alocados: list['RefProfessor']
        professores_visitantes: list['RefProfessor']

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

    cod: str
    """Código da disciplina"""
    nome: str
    """Nome da disciplina"""
    creditos: int
    """Quantidade de créditos da disciplina"""
    ofertas: dict[str, list[Oferta]]
    """Ofertas da disciplina por período"""

    def _get_key(self) -> str:
        return self.cod

    def __str__(self) -> str:
        return self.cod

    def merge_ofertas(self, periodo: str, other_ofertas: list[Oferta]):
            if periodo not in self.ofertas:
                self.ofertas[periodo] = other_ofertas
            else:
                for other_oferta in other_ofertas:
                    for oferta in self.ofertas[periodo]:
                        if other_oferta.turma == oferta.turma:
                            oferta.normal = oferta.normal or other_oferta.normal
                            oferta.professor_principal = oferta.professor_principal or other_oferta.professor_principal
                            oferta.professores_alocados = oferta.professores_alocados or other_oferta.professores_alocados
                            oferta.professores_visitantes = oferta.professores_visitantes or other_oferta.professores_visitantes
                            oferta.especial = oferta.especial or other_oferta.especial
                            oferta.horarios = oferta.horarios or other_oferta.horarios
                            oferta.semestre = oferta.semestre or other_oferta.semestre
                            oferta.bimestre = oferta.bimestre or other_oferta.bimestre
                            break
                    else:
                        self.ofertas[periodo].append(other_oferta)

    def _merge(self, other: Self) -> None:
        for periodo, ofertas in other.ofertas.items():
            self.merge_ofertas(periodo, ofertas)

class Cardapio(RefBy[date]):
    _key_type = date
    data: date

    class Refeicao(BaseModel):
        base: str
        guarnicao: str
        salada: str
        proteico: str
        vegetariano: str
        vegano: str
        observacao: str

    almoco: Optional[Refeicao] = None
    jantar: Optional[Refeicao] = None

    @field_serializer('data')
    def serialize_data(self, v: date) -> str:
        return v.isoformat()

    def _get_key(self) -> date:
        return self.data

    def _merge(self, other: Self):
        if self.almoco is None:
            self.almoco = other.almoco
        if self.jantar is None:
            self.jantar = other.jantar

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
    for cardapio in data['cardapios']:
        Cardapio(**cardapio)

def _dump(data: Iterable[BaseModel]) -> Any:
    return [d.model_dump() for d in data]

def dump() -> dict[str, Any]:
    return {
        'cursos': _dump(Curso._values()),
        'locais': _dump(Local._values()),
        'professores': _dump(Professor._values()),
        'disciplinas': _dump(Disciplina._values()),
        'periodos': _dump(Periodo._values()),
        'cardapios': _dump(Cardapio._values())
    }

class _RefDisciplina(Ref[str, Disciplina]):
    _ref_type = Disciplina
RefDisciplina = Annotated[str | _RefDisciplina | Disciplina, BeforeValidator(_RefDisciplina.r)]

class _RefCurso(Ref[str, Curso]):
    _ref_type = Curso
RefCurso = Annotated[str | _RefCurso | Curso, BeforeValidator(_RefCurso.r)]

class _RefLocal(Ref[str, Local]):
    _ref_type = Local
RefLocal = Annotated[str | _RefLocal | Local, BeforeValidator(_RefLocal.r)]

class _RefProfessor(Ref[str, Professor]):
    _ref_type = Professor
RefProfessor = Annotated[str | _RefProfessor | Professor, BeforeValidator(_RefProfessor.r)]

class _RefPeriodo(Ref[str, Periodo]):
    _ref_type = Periodo
RefPeriodo = Annotated[str | _RefPeriodo | Periodo, BeforeValidator(_RefPeriodo.r)]

class _RefCardapio(Ref[str, Cardapio]):
    _ref_type = Cardapio
RefCardapio = Annotated[str | _RefCardapio | Cardapio, BeforeValidator(_RefCardapio.r)]

__all__ = [
    "Curso",
    "Local",
    "Professor",
    "Disciplina",
    "load",
    "dump"
]
