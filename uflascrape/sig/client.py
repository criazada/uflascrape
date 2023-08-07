from pydantic import BaseModel
from typing import Optional, Mapping, Any
from httpx import Client, Response
from ..model import Curso, _RefDisciplina, Disciplina, Periodo, _RefPeriodo, RefDisciplina, RefPeriodo, Cardapio
from .parser import parse_html, get_cursos, list_matrizes, parse_matriz, parse_disciplina_pub, parse_oferta_pub, list_ofertas, parse_consulta_oferta, parse_oferta, get_periodos, parse_cardapio
from ..log import *
from datetime import date

SIG_BASE_URL = 'https://sig.ufla.br'
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/111.0'

def _replace(d: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    d = d.copy()
    d.update(kwargs)
    return d

_sig_modules: dict[str, 'SigModule'] = {}
class SigModule(BaseModel):
    name: str
    url: str
    requires_auth: bool = True

    @classmethod
    def get(cls, name: str) -> 'SigModule':
        return _sig_modules[name]

    def register(self):
        if self.name in _sig_modules:
            raise ValueError(f'SigModule {self.name} already registered')
        _sig_modules[self.name] = self

if not _sig_modules:
    SigModule(name='index', url='/').register()
    SigModule(name='login', url='/modulos/login/index.php', requires_auth=False).register()
    SigModule(name='logout', url='/modulos/login/sair.php').register()
    SigModule(name='rematricula', url='/modulos/alunos/rematricula/index.php').register()
    SigModule(name='consultar_horario', url='/modulos/alunos/rematricula/consultar_horario_disciplina.php').register()
    SigModule(name='consultar_horario_pub', url='/modulos/publico/horario_disciplina/horario_disciplina.php', requires_auth=False).register()
    SigModule(name='matrizes', url='/modulos/publico/matrizes_curriculares/index.php', requires_auth=False).register()
    SigModule(name='cardapio', url='/modulos/publico/praec/consultar_cardapios.php', requires_auth=False).register()

class Sig:
    def __init__(self,
                 *,
                 sig_url: str = SIG_BASE_URL,
                 user_agent: str = USER_AGENT):
        self._client = Client(base_url=sig_url, headers={'User-Agent': user_agent})
        self._logged_in = False
        self._last_csrf = ''
        self._last_disc: str = ''
        self._listed_once = False

    def _sig_request(self,
                     method: str,
                     module: str,
                     *,
                     data: Optional[Mapping[str, Any]]=None,
                     headers: Optional[Mapping[str, str]]=None,
                     params: Optional[Mapping[str, int|str]]=None) -> Response:
        sig_module = SigModule.get(module)
        if sig_module.requires_auth and not self._logged_in:
            raise RuntimeError(f'Cannot access {module} without logging in')

        r = self._client.request(method, sig_module.url, data=data, headers=headers, params=params)
        if r.status_code != 200:
            raise RuntimeError(f'Error requesting {module}: {r.status_code} {r.reason_phrase}')
        return r

    def login(self, username: str, password: str) -> bool:
        if self._logged_in:
            return True
        self._sig_request('GET', 'index')
        self._sig_request(
            'POST', 'login',
            data={
                'login': username,
                'senha': password,
                'lembrar_login': 0,
                'entrar': 'Entrar'
            }
        )
        self._logged_in = True
        return True

    def logout(self) -> bool:
        if not self._logged_in:
            return True
        self._sig_request('GET', 'logout')
        self._logged_in = False
        return True

    def get_cursos(self, get_matrizes=True) -> list[Curso]:
        info(f'Getting cursos ({get_matrizes=})')
        r = self._sig_request('GET', 'matrizes')
        root = parse_html(r.text)
        cursos = get_cursos(root)

        # return early if we don't need to get matrizes
        if not get_matrizes: return cursos

        # get matrizes
        for curso in cursos:
            curso.matrizes = self._get_matrizes(curso)
        return cursos

    def get_periodos(self) -> list[Periodo]:
        r = self._sig_request('GET', 'consultar_horario_pub')
        root = parse_html(r.text)
        return get_periodos(root)

    def _get_matrizes(self, curso: Curso) -> list[Curso.MatrizCurricular]:
        info(f'Getting matrizes for {curso}')
        r = self._sig_request(
            'POST', 'matrizes',
            params={'xml': 1},
            data={
                'cod_oferta_curso': curso.sig_cod_int,
                'enviar': 'Consultar'
            }
        )
        root = parse_html(r.text)
        cod_mats = list_matrizes(root)
        debug(f'Got matrizes {cod_mats=}')
        matrizes = []
        for cod_mat in cod_mats:
            info(f'Getting matriz {cod_mat=}')
            params = {'cod_matriz_curricular': cod_mat}
            r = self._sig_request('GET', 'matrizes', params=_replace(params, op='abrir'))
            matriz = parse_matriz(parse_html(r.text), cod_mat)
            r = self._sig_request('GET', 'matrizes', params=_replace(params, op='fechar'))
            matrizes.append(matriz)
        return matrizes

    def get_disciplina_pub(self, disc: RefDisciplina, periodo: RefPeriodo, get_ofertas: bool = True) -> Disciplina:
        info(f'Getting disciplina {disc} ({periodo}) ({get_ofertas=})')

        periodo = _RefPeriodo.d(periodo)
        cod_periodo = periodo.sig_cod_int
        r = self._sig_request(
            'POST', 'consultar_horario_pub',
            data={
                'codigo_disciplina': _RefDisciplina.r(disc).key,
                'cod_periodo_letivo': cod_periodo,
                'enviar': 'Consultar'
            },
            params={'xml': 1}
        )

        root = parse_html(r.text)
        d = parse_disciplina_pub(root)

        # return early if we don't need to get ofertas
        if not get_ofertas: return d

        ofertas = []
        cod_ofertas = list_ofertas(root)
        for cod_oferta in cod_ofertas:
            info(f'Getting oferta {cod_oferta=}')
            params = {'cod_oferta_disciplina': cod_oferta, 'cod_periodo_letivo': cod_periodo}
            r = self._sig_request(
                'GET', 'consultar_horario_pub',
                params=_replace(params, op='abrir')
            )
            root = parse_html(r.text)
            oferta = parse_oferta_pub(root)
            self._sig_request(
                'GET', 'consultar_horario_pub',
                params=_replace(params, op='fechar'),
            )
            ofertas.append(oferta)

        d.ofertas[periodo.key] = ofertas
        return d

    def list_ofertas(self,
                     matriz: bool = False,
                     modulo: str | int = 'T',
                     disciplina: Optional[RefDisciplina] = None,
                     nome: Optional[str] = None,
                     bimestre: Optional[str] = None) -> list[Disciplina.OfertaParcial]:
        if not self._listed_once:
            self._sig_request('GET', 'rematricula')
            r = self._sig_request('GET', 'consultar')
            self._listed_once = True
            root = parse_html(r.text)
            csrf, ofertas = parse_consulta_oferta(root)
            self._last_csrf = csrf

        disc = disciplina and _RefDisciplina.r(disciplina).key or ''

        r = self._sig_request(
            'POST', 'consultar',
            data={
                'pesquisar_matriz': 1 if matriz else 0,
                'modulo': modulo,
                'codigo': disc,
                'nome_disciplina': nome or '',
                'bimestre': bimestre or 'T',
                'token_csrf': self._last_csrf,
                'enviar': 'Consultar'
            }
        )

        root = parse_html(r.text)
        csrf, ofertas = parse_consulta_oferta(root)
        self._last_csrf = csrf
        self._last_disc = disc

        return ofertas

    def get_oferta(self, oferta: Disciplina.OfertaParcial) -> Disciplina.Oferta:
        if self._last_disc != _RefDisciplina.r(oferta.disc).key:
            self.list_ofertas(disciplina=oferta.disc)

        params = {'cod_oferta_disciplina': oferta.sig_cod_int}
        r = self._sig_request(
            'GET', 'consultar',
            params=_replace(params, op='abrir')
        )

        root = parse_html(r.text)
        parsed = parse_oferta(root)

        r = self._sig_request(
            'GET', 'consultar',
            params=_replace(params, op='fechar')
        )

        return parsed

    def get_cardapio(self, data: date) -> Cardapio:
        r = self._sig_request(
            'POST', 'cardapio',
            data={
                'data_dia': data.day,
                'data_mes': data.month,
                'data_ano': data.year,
                'enviar': 'Consultar'
            }
        )

        root = parse_html(r.text)
        return parse_cardapio(root, data)
