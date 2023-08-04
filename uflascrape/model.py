from pydantic import BaseModel, PlainSerializer, BeforeValidator
from typing import Optional, Annotated, Any

_cursos: dict[str, 'Curso'] = {}
class Curso(BaseModel):
  cod: str
  nome: str

  @classmethod
  def get(cls, cod: str) -> 'Curso':
    return _cursos[cod]

  @classmethod
  def load(cls, json: list[Any]):
    for curso in json:
      c = cls.model_validate(curso)
      _cursos[c.cod] = c

DumpCurso = Annotated[
  Curso, PlainSerializer(lambda x: x.cod, str), BeforeValidator(Curso.get)
]

class Professor(BaseModel):
  nome: str

_locais: dict[str, 'Local'] = {}
class Local(BaseModel):
  abbr: str
  local: str
  ocupacao: int

  @classmethod
  def get(cls, abbr: str) -> 'Local':
    return _locais[abbr]

  @classmethod
  def load(cls, json: list[Any]):
    for local in json:
      l = cls.model_validate(local)
      _locais[l.abbr] = l

DumpLocal = Annotated[
  Local, PlainSerializer(lambda x: x.abbr, str), BeforeValidator(Local.get)
]

class HorarioLocal(BaseModel):
  class Horario(BaseModel):
    dia: int
    hora: int
    minuto: int

  horario: Horario
  local: DumpLocal

class Oferta(BaseModel):
  class Vagas(BaseModel):
    oferecidas: int
    ocupadas: int
    restantes: int
    pendentes: int

  situacao: str
  curso: DumpCurso
  normal: Vagas
  especial: Vagas
  horarios: list[HorarioLocal]
  semestre: Optional[int] = None
  bimestre: Optional[str] = None

_disciplinas: dict[str, 'Disciplina'] = {}
class Disciplina(BaseModel):
  cod: str
  nome: str
  ofertas: list[Oferta]

  @classmethod
  def get(cls, cod: str) -> 'Disciplina':
    return _disciplinas[cod]
  
  @classmethod
  def load(cls, json: list[Any]):
    for disciplina in json:
      d = cls.model_validate(disciplina)
      _disciplinas[d.cod] = d

def load(json: dict[str, Any]):
  Curso.load(json['cursos'])
  Local.load(json['locais'])
  Disciplina.load(json['disciplinas'])
