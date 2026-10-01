import streamlit as st
import os
import re
import unicodedata
import tempfile
import shutil
import zipfile
import gc
import time

from pypdf import PdfReader, PdfWriter


# ============================================================
# CONFIGURAÇÃO
# ============================================================

st.set_page_config(
    page_title="Separador de Comprovantes",
    page_icon="📄",
    layout="wide"
)


# ============================================================
# CONSTANTES
# ============================================================

# Limite real desejado:
LIMITE_ZIP = 10 * 1024 * 1024

# Margem de segurança para cabeçalho/estrutura do ZIP.
# O resultado ficará normalmente abaixo de 10 MB.
LIMITE_SEGURANCA = 9_500_000


# ============================================================
# INTERFACE
# ============================================================

st.title("📄 Separador de Comprovantes")

st.write(
    """
    O sistema analisa o PDF página por página e identifica somente
    páginas que contenham os seguintes comprovantes:

    🔵 **COMPROVANTE PIX**

    🟢 **COMPROVANTE DE TRANSFERENCIA**

    🟣 **COMPROVANTE DE TRANSACAO BANCARIA**

    Cada comprovante identificado é extraído como uma página
    independente.

    Depois os PDFs são agrupados em arquivos ZIP de até aproximadamente
    **10 MB**.
    """
)

st.info(
    """
    💡 Para reduzir o consumo de memória, o sistema trabalha com
    arquivos temporários no disco e não mantém todos os PDFs
    simultaneamente na memória.
    """
)


# ============================================================
# NORMALIZAÇÃO
# ============================================================

def normalizar_texto(texto):

    if not texto:
        return ""

    texto = unicodedata.normalize(
        "NFKD",
        texto
    )

    texto = "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )

    texto = texto.upper()

    texto = re.sub(
        r"[^A-Z0-9]+",
        " ",
        texto
    )

    texto = re.sub(
        r"\s+",
        " ",
        texto
    )

    return texto.strip()


# ============================================================
# IDENTIFICA COMPROVANTE
# ============================================================

def identificar_comprovante(texto):

    texto = normalizar_texto(texto)

    if not texto:
        return None

    # ========================================================
    # 1 - COMPROVANTE PIX
    # ========================================================

    if re.search(
        r"\bCOMPROVANTE\s+PIX\b",
        texto
    ):
        return "PIX"

    if re.search(
        r"\bCOMPROVANTE\s+DE\s+PIX\b",
        texto
    ):
        return "PIX"

    # ========================================================
    # 2 - COMPROVANTE DE TRANSFERENCIA
    # ========================================================

    if re.search(
        r"\bCOMPROVANTE\s+DE\s+TRANSFERENCIA\b",
        texto
    ):
        return "TRANSFERENCIA"

    if re.search(
        r"\bCOMPROVANTE\s+TRANSFERENCIA\b",
        texto
    ):
        return "TRANSFERENCIA"

    # ========================================================
    # 3 - COMPROVANTE DE TRANSACAO BANCARIA
    # ========================================================

    if re.search(
        r"\bCOMPROVANTE\s+DE\s+TRANSACAO\s+BANCARIA\b",
        texto
    ):
        return "TRANSACAO_BANCARIA"

    if re.search(
        r"\bCOMPROVANTE\s+TRANSACAO\s+BANCARIA\b",
        texto
    ):
        return "TRANSACAO_BANCARIA"

    # ========================================================
    # NÃO É UM DOS COMPROVANTES SOLICITADOS
    # ========================================================

    return None


# ============================================================
# FORMATA TAMANHO
# ============================================================

def formatar_tamanho(tamanho):

    if tamanho < 1024:

        return f"{tamanho} B"

    if tamanho < 1024 * 1024:

        return (
            f"{tamanho / 1024:.2f} KB"
        )

    return (
        f"{tamanho / (1024 * 1024):.2f} MB"
    )


# ============================================================
# CRIA PDF DE UMA ÚNICA PÁGINA
# ============================================================

def criar_pdf_pagina(
    reader,
    numero_pagina,
    caminho_saida
):

    writer = PdfWriter()

    writer.add_page(
        reader.pages[numero_pagina]
    )

    with open(
        caminho_saida,
        "wb"
    ) as arquivo:

        writer.write(
            arquivo
        )

    del writer

    gc.collect()


# ============================================================
# CLASSE PARA CONTROLAR ZIP
# ============================================================

class GerenciadorZIP:

    def __init__(
        self,
        pasta_saida,
        prefixo
    ):

        self.pasta_saida = pasta_saida

        self.prefixo = prefixo

        self.numero = 1

        self.zip_file = None

        self.caminho_zip = None

        self.arquivos = []

        self.tamanho_atual = 0

        self.quantidade_arquivos = 0

        self._abrir_novo_zip()


    # ========================================================
    # ABRE NOVO ZIP
    # ========================================================

    def _abrir_novo_zip(self):

        nome = (
            f"{self.prefixo}_"
            f"{self.numero:03d}.zip"
        )

        self.caminho_zip = os.path.join(
            self.pasta_saida,
            nome
        )

        self.zip_file = zipfile.ZipFile(
            self.caminho_zip,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=1
        )

        self.tamanho_atual = 0

        self.quantidade_arquivos = 0


    # ========================================================
    # FECHA ZIP ATUAL
    # ========================================================

    def _fechar_zip(self):

        if self.zip_file is not None:

            self.zip_file.close()

            self.zip_file = None

        if (
            self.caminho_zip
            and os.path.exists(
                self.caminho_zip
            )
        ):

            tamanho = os.path.getsize(
                self.caminho_zip
            )

            if self.quantidade_arquivos > 0:

                self.arquivos.append({

                    "nome":
                        os.path.basename(
                            self.caminho_zip
                        ),

                    "caminho":
                        self.caminho_zip,

                    "tamanho":
                        tamanho,

                    "quantidade":
                        self.quantidade_arquivos
                })

            else:

                try:

                    os.remove(
                        self.caminho_zip
                    )

                except Exception:

                    pass


    # ========================================================
    # ADICIONA PDF AO ZIP
    # ========================================================

    def adicionar(
        self,
        caminho_pdf,
        nome_pdf,
        tamanho_pdf
    ):

        # ----------------------------------------------------
        # Tamanho atual do ZIP no disco
        # ----------------------------------------------------

        if os.path.exists(
            self.caminho_zip
        ):

            tamanho_atual_disco = os.path.getsize(
                self.caminho_zip
            )

        else:

            tamanho_atual_disco = 0

        # ----------------------------------------------------
        # Verifica se cabe
        # ----------------------------------------------------

        precisa_novo_zip = (

            self.quantidade_arquivos > 0
            and
            (
                tamanho_atual_disco
                +
                tamanho_pdf
                +
                4096
            )
            >
            LIMITE_SEGURANCA
        )

        # ----------------------------------------------------
        # Se não couber, fecha e abre outro
        # ----------------------------------------------------

        if precisa_novo_zip:

            self._fechar_zip()

            self.numero += 1

            self._abrir_novo_zip()

        # ----------------------------------------------------
        # Adiciona arquivo
        # ----------------------------------------------------

        self.zip_file.write(
            caminho_pdf,
            arcname=nome_pdf
        )

        self.quantidade_arquivos += 1

        # ----------------------------------------------------
        # Atualiza tamanho
        # ----------------------------------------------------

        self.zip_file.fp.flush()

        self.tamanho_atual = os.path.getsize(
            self.caminho_zip
        )

        # ----------------------------------------------------
        # Caso um único PDF seja maior que o limite
        # ----------------------------------------------------

        if (
            self.tamanho_atual
            >
            LIMITE_ZIP
        ):

            # Não é possível dividir um único PDF
            # de uma página sem alterar seu conteúdo.
            pass


    # ========================================================
    # FINALIZA
    # ========================================================

    def finalizar(self):

        self._fechar_zip()

        return self.arquivos


# ============================================================
# PROCESSAMENTO
# ============================================================

def processar_pdf(
    caminho_pdf,
    pasta_trabalho,
    progress_bar,
    status
):

    inicio = time.time()

    # ========================================================
    # LEITOR
    # ========================================================

    status.info(
        "📖 Abrindo PDF..."
    )

    reader = PdfReader(
        caminho_pdf,
        strict=False
    )

    total_paginas = len(
        reader.pages
    )

    # ========================================================
    # PASTAS
    # ========================================================

    pasta_saida = os.path.join(
        pasta_trabalho,
        "saida"
    )

    pasta_temp = os.path.join(
        pasta_trabalho,
        "temp"
    )

    os.makedirs(
        pasta_saida,
        exist_ok=True
    )

    os.makedirs(
        pasta_temp,
        exist_ok=True
    )

    # ========================================================
    # GERENCIADORES
    # ========================================================

    zip_comprovantes = GerenciadorZIP(
        pasta_saida,
        "COMPROVANTES"
    )

    zip_sem_comprovantes = GerenciadorZIP(
        pasta_saida,
        "SEM_COMPROVANTES"
    )

    # ========================================================
    # CONTADORES
    # ========================================================

    total_comprovantes = 0

    total_sem_comprovantes = 0

    quantidade_pix = 0

    quantidade_transferencia = 0

    quantidade_transacao = 0

    paginas_pix = []

    diagnostico = []

    # ========================================================
    # ANALISA PÁGINA POR PÁGINA
    # ========================================================

    for indice in range(
        total_paginas
    ):

        numero_pagina = indice + 1

        status.info(
            f"🔍 Analisando página "
            f"{numero_pagina} de "
            f"{total_paginas}..."
        )

        pagina = reader.pages[
            indice
        ]

        # ----------------------------------------------------
        # EXTRAÇÃO DO TEXT
```
