import argparse
import sys
import datetime
import requests
import logging
import dataclasses
import html
import html.parser
import traceback
import re
import json
from typing import Any
from logging import info, debug
from urllib.parse import urlencode
from dataclasses import asdict

DEFAULT_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/111.0'
DEFAULT_SIG_URL = 'https://sig.ufla.br{path}'
DEFAULT_SIG_MODULES = {
    'index': '/',
    'login': '/modulos/login/index.php',
    'logout': '/modulos/login/sair.php',
    'rematricula': '/modulos/alunos/rematricula/index.php',
    'consultar': '/modulos/alunos/rematricula/consultar_horario_disciplina.php'
}

oferta_re = re.compile(r'^(?P<disc>\w+) - (?P<nome>.*?) - (?P<turma>\w+)( \(((?P<bimestre>\d)º Bimestre|(?P<semestral>Semestral))\))?\s*$')
cod_oferta_re = re.compile(r'.*?cod_oferta_disciplina=(?P<cod>.*?)&op=(abrir|fechar).*')

@dataclasses.dataclass
class OfertaHead:
    cod: str
    disc: str
    nome: str
    turma: str
    bimestre: str
    semestral: bool

    @classmethod
    def from_text(cls, url: str, title: str):
        m = oferta_re.match(title)
        c = cod_oferta_re.match(url)

        if m is None:
            raise ValueError(f'{title} is not a valid offer name')
        if c is None:
            raise ValueError(f'{url} is not a valid offer URL')

        return OfertaHead(c.group('cod'),
                          m.group('disc'),
                          m.group('nome'),
                          m.group('turma'),
                          m.group('bimestre'),
                          m.group('semestral') is not None)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> 'OfertaHead':
        return OfertaHead(**d)

    def compress(self, discs: dict, turmas: dict, curso: int):
        if self.disc not in discs:
            discs[self.disc] = (self.nome, [])
        ofertas = discs[self.disc][1]

        if self.turma not in turmas:
            turmas[self.turma] = (len(turmas), curso)

        return ofertas, turmas[self.turma][0]

    def __str__(self) -> str:
        if self.bimestre:
            b = f' ({self.bimestre}º Bimestre)'
        elif self.semestral:
            b = f' (Semestral)'
        else:
            b = ''
        return f'{self.disc} - {self.nome} - {self.turma}{b} ({self.cod})'

@dataclasses.dataclass
class MatInfo:
    vagas_oferecidas: int
    vagas_ocupadas: int
    vagas_restantes: int
    solicitacoes_pendentes: int

    @classmethod
    def from_mat(cls, mat_info: dict[str, str]) -> 'MatInfo':
        return MatInfo(int(mat_info['Vagas oferecidas']),
                       int(mat_info['Vagas ocupadas']),
                       int(mat_info['Vagas restantes'].strip('*')),
                       int(mat_info['Solicitações Pendentes']))

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> 'MatInfo':
        return MatInfo(**d)

    def __str__(self) -> str:
        return (f'- Vagas Oferecidas: {self.vagas_oferecidas}\n'
                f'- Vagas Ocupadas: {self.vagas_ocupadas}\n'
                f'- Vagas Restantes: {self.vagas_restantes}\n'
                f'- Solicitações Pendentes: {self.solicitacoes_pendentes}')

dias = ['domingo', 'segunda-feira', 'terça-feira', 'quarta-feira', 'quinta-feira', 'sexta-feira', 'sábado', 'nenhum']

@dataclasses.dataclass
class Dia:
    num: int

    @classmethod
    def from_dia(cls, dia: str) -> 'Dia':
        dia = dia.lower()
        num = -1 if dia.startswith('sem') else dias.index(dia)
        return Dia(num)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> 'Dia':
        return Dia(d['num'])

    def __str__(self) -> str:
        return f'{dias[self.num]}'

@dataclasses.dataclass
class Horario:
    minuto: int

    @classmethod
    def from_hora(cls, hora: str) -> 'Horario':
        h, m = [int(x) for x in hora.split(':')]
        minuto = h * 60 + m
        return Horario(minuto)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> 'Horario':
        return Horario(**d)

    def __str__(self) -> str:
        m = self.minuto % 60
        h = self.minuto // 60
        return f'{h:02}:{m:02}'

@dataclasses.dataclass
class HorarioLocal:
    local: str
    abbr: str
    maximo: bool
    ocupacao: int
    tipo: str
    dia: Dia
    inicio: Horario
    fim: Horario

    @classmethod
    def from_info(cls, info: list[str]) -> 'HorarioLocal':
        horario = info[6]
        if horario == 'Sem horário definido':
            horario = '00:00 - 00:00'
        horas = horario.split(' - ')

        return HorarioLocal(local=info[0].strip(),
                            abbr=info[1],
                            maximo=info[2] == 'Sim',
                            ocupacao=int(info[3]),
                            tipo=info[4],
                            dia=Dia.from_dia(info[5]),
                            inicio=Horario.from_hora(horas[0]),
                            fim=Horario.from_hora(horas[1]))

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> 'HorarioLocal':
        c = d.copy()
        dia = Dia.from_dict(c.pop('dia'))
        inicio = Horario.from_dict(c.pop('inicio'))
        fim = Horario.from_dict(c.pop('fim'))
        return HorarioLocal(dia=dia, inicio=inicio, fim=fim, **c)

    def compress(self, horarios: list, salas: dict):
        if self.abbr not in salas:
            salas[self.abbr] = (len(salas), self.local)
        salaidx = salas[self.abbr][0]
        if self.tipo == 'Prática':
            tipo = 0
        elif self.tipo == 'Teórica':
            tipo = 1
        else:
            print(self.tipo)
            tipo = 2
        dia = self.dia.num
        inicio = self.inicio.minuto // 10
        fim = self.fim.minuto // 10
        horarios.append((salaidx, tipo, dia, inicio, fim))

    def __str__(self) -> str:
        return (f'{self.local} ({self.abbr}) - '
                f'{self.maximo} - '
                f'{self.ocupacao} - '
                f'{self.tipo} - '
                f'{self.dia} - '
                f'{self.inicio} - '
                f'{self.fim}')

@dataclasses.dataclass
class Oferta:
    head: OfertaHead
    situacao: str
    curso: str
    normal: MatInfo
    especial: MatInfo
    horarios: list[HorarioLocal]

    @classmethod
    def from_info(cls,
                  head: OfertaHead,
                  info: dict[str, str],
                  normal: dict[str, str],
                  especial: dict[str, str],
                  horarios: list[list[str]]):
        return Oferta(head,
                      situacao=info['Situação'],
                      curso=info['Oferta de Curso'],
                      normal=MatInfo.from_mat(normal),
                      especial=MatInfo.from_mat(especial),
                      horarios=[HorarioLocal.from_info(h) for h in horarios])

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> 'Oferta':
        c = d.copy()
        return Oferta(head=OfertaHead.from_dict(c.pop('head')),
                      normal=MatInfo.from_dict(c.pop('normal')),
                      especial=MatInfo.from_dict(c.pop('especial')),
                      horarios=[HorarioLocal.from_dict(h) for h in c.pop('horarios')],
                      **c)

    def compress(self,
                 discs: dict,
                 turmas: dict,
                 cursos: dict,
                 salas: dict):
        if self.curso not in cursos:
            cursos[self.curso] = len(cursos)

        ofertas, turmaidx = self.head.compress(discs, turmas, cursos[self.curso])
        horarios = []
        for horario in self.horarios:
            horario.compress(horarios, salas)
        ofertas.append((turmaidx, self.normal.vagas_restantes, self.especial.vagas_restantes, horarios))

    def __str__(self) -> str:
        hs = '\n'.join(str(h) for h in self.horarios)
        return (f'{self.head}\n'
                f'{self.situacao}\n'
                f'Matrícula Normal:\n{self.normal}\n'
                f'Matrícula Especial:\n{self.especial}\n'
                f'{hs}\n')

class ConsultaParser(html.parser.HTMLParser):
    def reset(self) -> None:
        super().reset()
        self.ofertas: list[OfertaHead] = []
        self.csrf: None | str = None

    def handle_atag(self, attrs: list[tuple[str, str | None]]) -> None:
        title = None
        url = None
        for k, v in attrs:
            if v is None: continue
            if k == 'href' and 'cod_oferta_disciplina' in v:
                url = v
            if k == 'title':
                title = v
        if not title or not url: return
        self.ofertas.append(OfertaHead.from_text(url, title))

    def handle_inputtag(self, attrs: list[tuple[str, str | None]]) -> None:
        is_token = False
        token = None
        for k, v in attrs:
            if (k, v) == ('name', 'token_csrf'):
                is_token = True
            if k == 'value':
                token = v
        if not is_token or not token: return
        self.csrf = token

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == 'a': self.handle_atag(attrs)
        if tag == 'input': self.handle_inputtag(attrs)

class OfertaParser(html.parser.HTMLParser):
    def reset(self) -> None:
        super().reset()
        self.info = {}
        self.info_normal = {}
        self.info_especial = {}
        self.extra_info = {}
        self._current_info = self.info
        self._current_data = None
        self._inside = {
            'p': False,
            'strong': False,
            'tr': False,
            'td': False,
            'abbr': False,
            'thead': False,
        }
        self.rows = []
        self._current_row = []
        self._current_abbr = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._inside: self._inside[tag] = True
        if tag == 'fieldset':
            for attr in attrs:
                if attr == ('class', 'vagas_normais'):
                    self._current_info = self.info_normal
                elif attr == ('class', 'vagas_especiais'):
                    self._current_info = self.info_especial
        if tag == 'abbr':
            for k, v in attrs:
                if k == 'title':
                    self._current_abbr = v

    def handle_endtag(self, tag: str) -> None:
        if tag in self._inside: self._inside[tag] = False
        if tag == 'p':
            self._current_data = None
        if tag == 'fieldset':
            if self._current_info is self.info_especial:
                self._current_info = self.extra_info

        if tag == 'tr' and not self._inside['thead']:
            self.rows.append(self._current_row)
            self._current_row = []

    def handle_data(self, data: str) -> None:
        if self._inside['p'] and self._inside['strong']:
            self._current_data = data
        if self._inside['p'] and self._current_data:
            self._current_info[self._current_data[:-1]] = data.strip()

        if self._inside['td'] and self._inside['abbr']:
            self._current_row.append(self._current_abbr)
        if self._inside['td']:
            self._current_row.append(data)

class Sig:
    def __init__(self,
                 *,
                 sig_url: str = DEFAULT_SIG_URL,
                 sig_modules: dict[str, str] = DEFAULT_SIG_MODULES,
                 user_agent: str = DEFAULT_USER_AGENT) -> None:
        self._session = requests.Session()
        self._session.headers['User-Agent'] = user_agent
        self._base_url = sig_url
        self._modules = sig_modules
        self._listed_once = False
        self._last_url = None
        self._last_csrf = None
        self._consulta_parser = ConsultaParser()
        self._oferta_parser = OfertaParser()

    def _sig_request(self, method: str, module: str, *, err_not_ok: bool = True, data = None, headers = None, **kwargs):
        if method == 'POST' and data is not None:
            if headers is None:
                headers = {}
            if isinstance(data, dict):
                data = urlencode(data)
            headers['Content-Type'] = 'application/x-www-form-urlencoded'

        url = self._base_url.format(path=self._modules[module])
        self._last_url = url

        r = self._session.request(
            method,
            url,
            headers=headers,
            data=data,
            **kwargs
        )

        debug(f'sig_request {method} {module} {r.status_code}')
        if err_not_ok and r.status_code != 200:
            raise RuntimeError(f'{method} {module} {r.status_code}')
        return r

    def _sig_get(self, module: str, *args, **kwargs):
        return self._sig_request('GET', module, *args, **kwargs)

    def _sig_post(self, module: str, *args, **kwargs):
        return self._sig_request('POST', module, *args, **kwargs)

    def login(self, user, password) -> bool:
        self._sig_get('index')
        self._sig_post(
            'login',
            data={
                'login': user,
                'senha': password,
                'lembrar_login': 0,
                'entrar': 'Entrar'
            })
        return True

    def get_ofertas(self,
                    matriz: bool = False,
                    modulo: str | int = 'T',
                    disciplina: str | None = None,
                    nome: str | None = None,
                    bimestre: str | None = None) -> list[OfertaHead]:
        if not self._listed_once:
            self._sig_get('rematricula')
            r = self._sig_get('consultar')
            self._listed_once = True

            self._consulta_parser.reset()
            self._consulta_parser.feed(r.text)
            self._last_csrf = self._consulta_parser.csrf

        r = self._sig_post(
            'consultar',
            data={
                'pesquisar_matriz': 1 if matriz else 0,
                'modulo': modulo,
                'codigo': disciplina if disciplina else '',
                'nome_disciplina': nome if nome else '',
                'bimestre': bimestre if bimestre else 'T',
                'token_csrf': self._last_csrf,
                'enviar': 'Consultar'
            }
        )

        self._consulta_parser.reset()
        self._consulta_parser.feed(html.unescape(r.text))
        self._last_csrf = self._consulta_parser.csrf
        self._last_cod = disciplina
        return self._consulta_parser.ofertas[:]

    def get_oferta(self, oferta: OfertaHead) -> Oferta:
        if self._last_cod != oferta.disc:
            self.get_ofertas(disciplina=oferta.disc)

        params = {'cod_oferta_disciplina': oferta.cod}

        self._oferta_parser.reset()
        params['op'] = 'abrir'
        r = self._sig_get('consultar', params=params)

        self._oferta_parser.feed(html.unescape(r.text))
        new_oferta = Oferta.from_info(
            oferta,
            self._oferta_parser.info,
            self._oferta_parser.info_normal,
            self._oferta_parser.info_especial,
            self._oferta_parser.rows
        )

        params['op'] = 'fechar'
        self._sig_get('consultar', params=params)
        return new_oferta

    def logout(self) -> bool:
        self._sig_get('logout')
        return True

def main(prog: str, argv: list[str]):
    parser = argparse.ArgumentParser(
        prog=prog,
        description='Obtenha dados do SIG/UFLA.',
        epilog='''
            Código fonte disponível em https://github.com/criazada/uflascrape.
            Suas informações de login são enviadas somente para sig.ufla.br''',
        add_help=False
    )

    parser.add_argument('-h', '--help',
                        help='exibe esta mensagem de ajuda', action='store_true')
    parser.add_argument('-s', '--salvar',
                        help='salva os resultados das operações em um arquivo',
                        metavar='ARQUIVO', type=argparse.FileType('r+', encoding='utf-8'))

    auth = parser.add_argument_group('autenticação', 'opções de autenticação').add_mutually_exclusive_group()
    auth.add_argument('-l', '--login',
                      help='seu login do SIG no formato usuario:senha')
    auth.add_argument('-a', '--arquivo-login',
                      help='arquivo contendo seu usuário e senha no formato usuario:senha',
                      metavar='ARQUIVO', type=argparse.FileType('r', encoding='utf-8'))

    ofert = parser.add_argument_group('ofertas', 'opções para busca de ofertas (requer autenticação)')
    ofert.add_argument('--buscar-ofertas',
                       help='realiza uma busca de ofertas com as possíveis seguintes opções',
                       action='store_true')
    ofert.add_argument('--matriz',
                       help='realizar busca somente na sua matriz curricular',
                       action='store_true')
    ofert.add_argument('--periodo',
                       help='buscar por matérias no período PERIODO da sua matriz (deve ser utilizado junto com --matriz)',
                       choices=['todos', 'eletivas', 1, 2, 3, 4, 5, 6, 7, 8, 9, 10], default='todos')
    ofert.add_argument('--disciplina',
                       help='código da disciplina (ex GCC123)',
                       metavar='CODIGO')
    ofert.add_argument('--nome',
                       help='nome da disciplina')
    ofert.add_argument('--oferta',
                       help='tipo de oferta',
                       choices=['todos', 'semestral', '1b', '2b'], default='todos')

    horas = parser.add_argument_group('horários', 'opções para obtenção de horários e locais de ofertas (requer autenticação)')
    horas.add_argument('--buscar-horarios',
                       help='buscar horários de ofertas de disciplinas',
                       action='store_true')
    horas.add_argument('--ofertas',
                       help='arquivo com ofertas desejadas',
                       metavar='ARQUIVO',
                       type=argparse.FileType('r', encoding='utf-8'))
    horas.add_argument('--horarios',
                       help='arquivo com horários',
                       metavar='ARQUIVO',
                       type=argparse.FileType('r', encoding='utf-8'))
    horas.add_argument('--exportar-horarios',
                       help='exportar arquivo para uso na ferramenta web',
                       metavar='ARQUIVO',
                       type=argparse.FileType('w', encoding='utf-8'))

    args = parser.parse_args(argv)

    if args.help:
        parser.print_help()
        return

    if args.salvar:
        args.salvar.seek(0, 2)
        if args.salvar.tell() < 2:
            args.salvar.seek(0)
            json.dump({}, args.salvar)

    login = args.login or args.arquivo_login
    sig = Sig()
    try:
        if login:
            t = args.login if args.login else args.arquivo_login.read()
            parts = t.strip().split(':')
            user = parts[0]
            password = ':'.join(parts[1:])
            sig.login(user, password)

        ofertas: list[OfertaHead] = []
        horarios: list[Oferta] = []

        if args.salvar:
            args.salvar.seek(0)
            data = json.load(args.salvar)

            if 'ofertas' in data:
                ofertas = [OfertaHead.from_dict(h) for h in data['ofertas']]
            if 'horarios' in data:
                horarios = [Oferta.from_dict(h) for h in data['horarios']]

        if args.buscar_ofertas:
            if not login:
                print('É necessário se autenticar para realizar busca de ofertas')
                return

            matriz = args.matriz
            periodo = args.periodo
            disciplina = args.disciplina
            nome = args.nome
            oferta = args.oferta

            map_periodo = {
                'todos': 'T',
                'eletivas': 'e'
            }
            periodo = map_periodo.get(periodo, periodo)

            map_oferta = {
                'semestral': 3,
                '1b': 1,
                '2b': 2,
                'todos': 'T'
            }
            oferta = map_oferta[oferta]

            ofertas = sig.get_ofertas(matriz, periodo, disciplina, nome, oferta)

            if args.salvar:
                args.salvar.seek(0)
                data = json.load(args.salvar)

                data['ofertas'] = [asdict(o) for o in ofertas]

                args.salvar.seek(0)
                json.dump(data, args.salvar)

        if args.buscar_horarios:
            if args.ofertas:
                data = json.load(args.ofertas)
                ofertas = [OfertaHead.from_dict(h) for h in data['ofertas']]

            for i, oferta in enumerate(ofertas):
                if args.salvar:
                    print(f'Obtendo horário para {oferta} ({i+1}/{len(ofertas)})')
                oferta_full = sig.get_oferta(oferta)
                if not args.salvar:
                    print(oferta_full)
                horarios.append(oferta_full)

            if args.salvar:
                args.salvar.seek(0)
                data = json.load(args.salvar)

                data['horarios'] = [asdict(h) for h in horarios]

                args.salvar.seek(0)
                json.dump(data, args.salvar)

        if args.exportar_horarios:
            if args.horarios:
                data = json.load(args.horarios)
                horarios = [Oferta.from_dict(h) for h in data['horarios']]

            c_discs = {}
            d_turmas = {}
            d_cursos = {}
            d_salas = {}

            for oferta in horarios:
                oferta.compress(c_discs, d_turmas, d_cursos, d_salas)

            c_turmas = [(k, v[1]) for k, v in d_turmas.items()]
            c_cursos = list(d_cursos.keys())
            c_salas = [(k, v[1]) for k, v in d_salas.items()]
            compressed = {
                'd': c_discs,
                't': c_turmas,
                'c': c_cursos,
                's': c_salas
            }
            json.dump(compressed, args.exportar_horarios, separators=(',', ':'))
    except:
        traceback.print_exc()

    finally:
        if login:
            sig.logout()

if __name__ == '__main__':
    main(sys.argv[0], sys.argv[1:])
