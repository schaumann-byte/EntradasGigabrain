"""Preparação do dataset PURE como banco de testes para o módulo de ingestão
de um sistema multiagente de Engenharia de Requisitos.

Gera pares (entrada, gabarito) a partir dos XMLs do PURE, nos modos
``context``, ``notes`` e ``dialogue`` (formato v1, congelado) e ``meetings``
(várias reuniões com fenômenos de requisitos, schema 2.0).
"""

import sys

__version__ = "0.2.0"

# versão registrada nos gabaritos dos modos v1; fica fixa para que o dataset
# v1 continue reproduzível byte a byte (ver tests/test_regression_v1.py)
V1_VERSION = "0.1.0"


def utf8_stdio():
    """Força UTF-8 na saída dos comandos. Sem isso, o ``--help`` e as mensagens
    com acento quebram (``UnicodeEncodeError``) quando a saída do Windows é
    cp1252, por exemplo no Git Bash ou redirecionada para arquivo."""
    for stream in (sys.stdout, sys.stderr):
        if (getattr(stream, "encoding", "") or "").lower().replace("-", "") != "utf8":
            stream.reconfigure(encoding="utf-8")
