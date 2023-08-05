from pydantic import BaseModel
from typing import Optional, Mapping, Any
from httpx import Client, Response
from ..model import Curso
from .parser import parse_html, get_cursos, list_matrizes, parse_matriz
from ..log import *

SIG_BASE_URL = 'https://sig.ufla.br'
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/111.0'

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
    SigModule(name='consultar_horario_pub', url='/modulos/alunos/rematricula/consultar_horario_disciplina.php').register()
    SigModule(name='matrizes', url='/modulos/publico/matrizes_curriculares/index.php', requires_auth=False).register()

class Sig:
    def __init__(self,
                 *,
                 sig_url: str = SIG_BASE_URL,
                 user_agent: str = USER_AGENT):
        self._client = Client(base_url=sig_url, headers={'User-Agent': user_agent})
        self._logged_in = False

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
        if get_matrizes:
            for curso in cursos:
                curso.save()
                curso.matrizes = self._get_matrizes(curso)
        return cursos

    def _get_matrizes(self, curso: Curso) -> list[Curso.MatrizCurricular]:
        info(f'Getting matrizes for {curso=}')
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
            r = self._sig_request(
                'GET', 'matrizes',
                params={'cod_matriz_curricular': cod_mat, 'op': 'abrir'}
            )
            matriz = parse_matriz(parse_html(r.text), cod_mat)
            r = self._sig_request(
                'GET', 'matrizes',
                params={'cod_matriz_curricular': cod_mat, 'op': 'fechar'}
            )
            matrizes.append(matriz)
        return matrizes