import html
import html.parser
from pydantic import BaseModel, Field
from typing import Optional, Generator, Callable
from ..model import Curso, CursoCell, Disciplina, DisciplinaCell, Local, LocalCell, Professor, ProfessorCell
import re
from ..log import *

class Tag(BaseModel):
    name: str
    children: list['Tag'] = Field(default_factory=list)
    classes: list[str] = Field(default_factory=list)
    id: Optional[str] = None
    content: Optional[str] = None
    attrs: dict[str, str | None] = Field(default_factory=dict)

    @property
    def text(self) -> str:
        return self.content or ''

    def filter_children(self, filter: Callable[['Tag'], bool], recursive: bool = True) -> Generator['Tag', None, None]:
        for child in self.children:
            if filter(child):
                yield child
            if recursive:
                yield from child.filter_children(filter, recursive=True)

    def all_children(self, recursive: bool = True) -> Generator['Tag', None, None]:
        return self.filter_children(lambda _: True, recursive=recursive)

    def find_by_name(self, name: str, recursive: bool = True) -> list['Tag']:
        return list(self.filter_children(lambda tag: tag.name == name, recursive=recursive))

    def find_by_id(self, id: str, recursive: bool = True) -> Optional['Tag']:
        for tag in self.all_children(recursive=recursive):
            if tag.id == id:
                return tag
        return None

    def find_by_class(self, class_: str, recursive: bool = True) -> list['Tag']:
        return list(self.filter_children(lambda tag: class_ in tag.classes, recursive=recursive))

    def __getitem__(self, name: str) -> Optional[str]:
        return self.attrs.get(name)

self_closing = {
    'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link',
    'meta', 'param', 'source', 'track', 'wbr', 'command', 'keygen', 'menuitem', 'frame'
}

class HtmlParser(html.parser.HTMLParser):
    def reset(self) -> None:
        super().reset()
        self._root = Tag(name="#root")
        self._stack = [self._root]

    @property
    def _current(self) -> Tag:
        return self._stack[-1]

    def handle_starttag(self, tag_name: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = Tag(name=tag_name)
        self._current.children.append(tag)
        if tag_name not in self_closing:
            self._stack.append(tag)

        for attr, value in attrs:
            if attr == 'class':
                if value is not None:
                    tag.classes.extend(value.split())
            elif attr == 'id':
                tag.id = value
            else:
                tag.attrs[attr] = value

    def handle_endtag(self, tag_name: str) -> None:
        if tag_name in self_closing:
            return

        tag = self._stack.pop()
        if tag.name != tag_name:
            raise RuntimeError(f'Expected end tag {tag.name}, got {tag_name}')

    def handle_data(self, data: str) -> None:
        data = data.strip()
        if data:
            self._current.content = data

def parse_html(html: str) -> Tag:
    parser = HtmlParser()
    parser.feed(html)
    return parser._root

def sig_fields(dados: Tag) -> dict[str, str]:
    ps = dados.find_by_name('p')
    fields = {}
    for p in ps:
        if not p.text: continue
        strong = p.find_by_name('strong')
        if not strong: continue
        if not strong[0].text: continue
        key = strong[0].text.strip(':').lower()
        val = p.text.strip()
        fields[key] = val
    return fields

def extract_links_re(root: Tag, rg: re.Pattern) -> list[str]:
    anchors = root.find_by_name('a')
    links = []
    for anchor in anchors:
        href = anchor['href']
        if href is None: continue
        g = rg.match(href)
        if not g: continue
        links.append(g.group('extract'))
    return links

def get_cursos(root: Tag) -> list[Curso]:
    select = root.find_by_id('cod_oferta_curso')
    if not select:
        raise RuntimeError('Could not find select tag')
    cursos = []
    for option in select.find_by_name('option'):
        sig_int = option['value'] or '-1'
        title = option['title']
        assert title is not None
        cod, nome = title.split(' - ')
        curso = Curso.get(cod)
        curso = curso if curso else Curso(cod=cod, sig_cod_int=int(sig_int), nome=nome)
        cursos.append(curso)
    return cursos

matriz_link_re = re.compile(r'^.*?cod_matriz_curricular=(?P<extract>.*?)&op=(abrir|fechar)')
def list_matrizes(root: Tag) -> list[int]:
    return [int(cod) for cod in extract_links_re(root, matriz_link_re)]

Row = list[Tag]
Group = list[Row]
Table = list[Group]
def parse_table(table: Tag) -> Table:
    current_group: Group = []
    first = True
    groups: list[Group] = [current_group]
    for child in table.children:
        if child.name == 'thead':
            if not first:
                current_group = []
                groups.append(current_group)
            first = False
        elif child.name == 'tbody':
            for table_row in child.find_by_name('tr'):
                current_group.append(table_row.find_by_name('td'))
    return groups

Reqs = list[str]
class DisciplinaRow(BaseModel):
    cod: str
    nome: str
    creditos: int
    percentual: float
    forte: Reqs
    minimo: Reqs
    coreq: Reqs

def parse_disciplina_row(row: Row) -> DisciplinaRow:
    def parse_reqs(cell: Tag) -> Reqs:
        return [abbr.text for abbr in cell.find_by_name('abbr')]

    cod, nome, creds, percent, forte, minimo, coreq, ementa = row
    cod = cod.text
    nome = nome.text
    creds = int(creds.text)
    percent = float(percent.text.replace(',', '.')) if '-' not in percent.text else 0
    forte = parse_reqs(forte)
    minimo = parse_reqs(minimo)
    coreq = parse_reqs(coreq)

    return DisciplinaRow(
        cod=cod,
        nome=nome,
        creditos=creds,
        percentual=percent,
        forte=forte,
        minimo=minimo,
        coreq=coreq,
    )

def parse_matriz(root: Tag, sig_cod_int: int) -> Curso.MatrizCurricular:
    dados = root.find_by_class('dados')[0]
    fields = sig_fields(dados)

    nome = fields['nome']
    descricao = fields['descrição']
    periodos = int(fields['quantidade de períodos'])
    minimo = int(fields['mínimo de períodos letivos'])
    maximo = int(fields['máximo de períodos letivos'])
    vagas = int(fields['quantidade de vagas semestrais'])

    tables = root.find_by_name('table')
    eletivas_raw = tables[3] if len(tables) >= 4 else None
    if eletivas_raw:
        categorias: dict[int, str] = {}
        categorias_headers = eletivas_raw.filter_children(lambda tag: tag.name == 'th' and tag['colspan'] == '8')
        for i, t in enumerate(categorias_headers):
            categorias[i] = t.text
    else:
        categorias = {}

    tables = [parse_table(table) for table in tables]
    carga_horaria = tables[0]
    exigencia_eletivas = tables[1]
    obrigatorias = tables[2]
    if eletivas_raw:
        eletivas = tables[3]
    else:
        eletivas = []
    # estagios = tables[4]

    def ensure_existence(row: DisciplinaRow):
        if not Disciplina.get(row.cod):
            d = Disciplina(cod=row.cod, nome=row.nome, creditos=row.creditos)
            d.save()

    def group_to_rowlist(group: Group) -> list[DisciplinaRow]:
        return [parse_disciplina_row(row) for row in group if len(row) == 8]

    def ensure_rowlist(l: list[DisciplinaRow]):
        for row in l:
            ensure_existence(row)
        return l

    obrigatorias_parsed = [ensure_rowlist(group_to_rowlist(group)) for group in obrigatorias][1:]
    eletivas_parsed = [ensure_rowlist(group_to_rowlist(group)) for group in eletivas][1:]

    def get_disciplinas(l: list[str]) -> list[DisciplinaCell]:
        disciplinas: list[Disciplina | str] = []
        for d in l:
            disc = Disciplina.get(d)
            if not disc:
                warning(f'Disciplina {d} does not exist')
            disciplinas.append(disc or d)
        return [DisciplinaCell(disc=c) for c in disciplinas]

    def row_to_matriz(row: DisciplinaRow) -> Curso.MatrizCurricular.DisciplinaMatriz:
        d = Disciplina.get(row.cod)
        if not d:
            raise RuntimeError(f'Disciplina {row.cod} does not exist')

        fortes = get_disciplinas(row.forte)
        minimos = get_disciplinas(row.minimo)
        coreqs = get_disciplinas(row.coreq)
        return Curso.MatrizCurricular.DisciplinaMatriz(
            disc=d.cell(),
            percentual=row.percentual,
            reqs_fortes=fortes,
            reqs_minimos=minimos,
            coreqs=coreqs,
        )

    def group_to_matriz(group: list[DisciplinaRow]) -> list[Curso.MatrizCurricular.DisciplinaMatriz]:
        return [row_to_matriz(row) for row in group]

    DisciplinasMatriz = list[Curso.MatrizCurricular.DisciplinaMatriz]
    r_obrigatorias: dict[int, DisciplinasMatriz] = {}
    for i, group in enumerate(obrigatorias_parsed):
        r_obrigatorias[i+1] = group_to_matriz(group)

    r_eletivas: dict[str, DisciplinasMatriz] = {}
    for i, group in enumerate(eletivas_parsed):
        if not group: continue
        r_eletivas[categorias[i]] = group_to_matriz(group)

    return Curso.MatrizCurricular(
        cod=nome.replace('/', ''),
        sig_cod_int=sig_cod_int,
        nome=nome,
        descricao=descricao,
        periodos=periodos,
        min_periodos=minimo,
        max_periodos=maximo,
        vagas=vagas,
        obrigatorias=r_obrigatorias,
        eletivas=r_eletivas,
    )

def parse_disciplina_pub(root: Tag) -> Disciplina:
    dados = root.find_by_class('dados')[0]
    fields = sig_fields(dados)

    nome = fields['nome']
    codigo = fields['código']
    creditos = int(fields['créditos'])
    h_teoricas = int(fields['horas teóricas'])
    h_praticas = int(fields['horas práticas'])
    oferecimento = fields['oferecimento']

    d = Disciplina(
        cod=codigo,
        nome=nome,
        creditos=creditos,
    )
    d.save()
    return d

_oferta_re = re.compile(r'^.*?cod_oferta_disciplina=(?P<extract>.*?)&.*?&op=(abrir|fechar)')
def list_ofertas(root: Tag) -> list[int]:
    return [int(cod) for cod in extract_links_re(root, _oferta_re)]

_oferta_pub_name_re = re.compile(r'^(?P<nome>.*?)( \(Capacidade Original:? (?P<capacidade>\d+)\))?$')
def parse_oferta_pub(root: Tag) -> Disciplina.Oferta:
    fields = sig_fields(root)
    turma = fields['turma']
    curso = fields['oferta de curso'].split(' - ')[0]
    prof = fields['docente principal'].split(' (')[0]
    situacao = fields['situação']

    HorarioLocal = Disciplina.Oferta.HorarioLocal
    horarios: list[HorarioLocal] = []
    table = root.find_by_name('table')[0]
    rows = parse_table(table)[0]

    for dia in range(1, 8):
        inicio: Optional[HorarioLocal.Horario] = None
        fim: Optional[HorarioLocal.Horario] = None
        local: Optional[Local] = None

        for i, row in enumerate(rows):
            hora = i+7
            div = row[dia].find_by_class('ocupado')
            if not div: continue
            abbrs = div[0].find_by_name('abbr')
            nome_cap = abbrs[0]['title']
            if not nome_cap:
                warning(f'abbr is empty for {hora=}, {dia=}')
                continue
            g = _oferta_pub_name_re.match(nome_cap)
            if not g:
                warning(f'Could not match {nome_cap=}')
                continue
            nome = g.group('nome')
            cap = g.group('capacidade')
            capacidade = int(cap) if cap else -1

            abbr = abbrs[0].text

            local = Local.get(abbr)
            if not local:
                local = local if local else Local(abbr=abbr, local=nome, ocupacao=capacidade)
                local.save()

            if inicio:
                hora += 1

            h = HorarioLocal.Horario(
                dia=dia-1,
                hora=hora,
                minuto=0)
            if inicio is None:
                inicio = h
            fim = h

        if inicio is not None and fim is not None and local is not None:
            hl = HorarioLocal(
                inicio=inicio,
                fim=fim,
                local=local
            )
            horarios.append(hl)

    return Disciplina.Oferta(
        situacao=situacao,
        curso=CursoCell(curso=curso),
        horarios=horarios,
        turma=turma,
        professor=ProfessorCell(prof=prof),
    )
