```python
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
    page_title="Separador de Documentos Comprobatórios e Comprovante",
    page_icon="📄",
    layout="wide"
)


# ============================================================
# CONSTANTES
# ============================================================

# Limite máximo desejado
LIMITE_ZIP = 10 * 1024 * 1024

# Margem de segurança para manter o ZIP abaixo de 10 MB
LIMITE_SEGURANCA = 9_500_000


# ============================================================
# CSS
# ============================================================

st.markdown(
    """
    <style>

    .rodape {
        text-align: center;
        margin-top: 60px;
        padding: 18px 0;
        color: #888888;
        font-size: 14px;
        border-top: 1px solid #444444;
    }

    .rodape strong {
        color: #aaaaaa;
    }

    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# INTERFACE
# ============================================================

st.title(
    "📄 Separador de Documentos Comprobatórios e Comprovante"
)

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

    padroes_pix = [

        r"\bCOMPROVANTE\s+PIX\b",

        r"\bCOMPROVANTE\s+DE\s+PIX\b",

        r"\bCOMPROVANTE\s+DO\s+PIX\b",

        r"\bPIX\s+REALIZADO\b",

        r"\bPIX\s+EFETUADO\b",

        r"\bPAGAMENTO\s+PIX\b",

        r"\bPIX\s+ENVIADO\b",

        r"\bPIX\s+RECEBIDO\b",

        r"\bTRANSACAO\s+PIX\b",

        r"\bTRANSFERENCIA\s+VIA\s+PIX\b",

    ]

    for padrao in padroes_pix:

        if re.search(
            padrao,
            texto
        ):

            return "PIX"


    # ========================================================
    # 2 - COMPROVANTE DE TRANSFERENCIA
    # ========================================================

    padroes_transferencia = [

        r"\bCOMPROVANTE\s+DE\s+TRANSFERENCIA\b",

        r"\bCOMPROVANTE\s+TRANSFERENCIA\b",

        r"\bCOMPROVANTE\s+DA\s+TRANSFERENCIA\b",

        r"\bTRANSFERENCIA\s+REALIZADA\b",

        r"\bTRANSFERENCIA\s+EFETUADA\b",

        r"\bTRANSFERENCIA\s+BANCARIA\b",

        r"\bTRANSFERENCIA\s+ELETRONICA\b",

        r"\bTRANSFERENCIA\s+CONCLUIDA\b",

        r"\bCOMPROVANTE\s+TED\b",

        r"\bCOMPROVANTE\s+DOC\b",

        r"\bTED\s+REALIZADA\b",

        r"\bTED\s+EFETUADA\b",

        r"\bDOC\s+REALIZADO\b",

        r"\bDOC\s+EFETUADO\b",

    ]

    for padrao in padroes_transferencia:

        if re.search(
            padrao,
            texto
        ):

            return "TRANSFERENCIA"


    # ========================================================
    # 3 - COMPROVANTE DE TRANSACAO BANCARIA
    # ========================================================

    padroes_transacao = [

        r"\bCOMPROVANTE\s+DE\s+TRANSACAO\s+BANCARIA\b",

        r"\bCOMPROVANTE\s+TRANSACAO\s+BANCARIA\b",

        r"\bCOMPROVANTE\s+DE\s+TRANSACAO\b",

        r"\bTRANSACAO\s+BANCARIA\b",

        r"\bTRANSACAO\s+REALIZADA\b",

        r"\bTRANSACAO\s+EFETUADA\b",

        r"\bTRANSACAO\s+CONCLUIDA\b",

    ]

    for padrao in padroes_transacao:

        if re.search(
            padrao,
            texto
        ):

            return "TRANSACAO_BANCARIA"


    # ========================================================
    # NÃO É COMPROVANTE
    # ========================================================

    return None


# ============================================================
# FORMATA TAMANHO
# ============================================================

def formatar_tamanho(tamanho):

    if tamanho is None:
        return "0 B"

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

        if os.path.exists(
            self.caminho_zip
        ):

            tamanho_atual_disco = os.path.getsize(
                self.caminho_zip
            )

        else:

            tamanho_atual_disco = 0


        # ====================================================
        # VERIFICA SE CABE NO ZIP
        # ====================================================

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


        # ====================================================
        # ABRE NOVO ZIP
        # ====================================================

        if precisa_novo_zip:

            self._fechar_zip()

            self.numero += 1

            self._abrir_novo_zip()


        # ====================================================
        # ADICIONA PDF
        # ====================================================

        self.zip_file.write(
            caminho_pdf,
            arcname=nome_pdf
        )

        self.quantidade_arquivos += 1


        # ====================================================
        # ATUALIZA TAMANHO
        # ====================================================

        try:

            self.zip_file.fp.flush()

        except Exception:

            pass

        self.tamanho_atual = os.path.getsize(
            self.caminho_zip
        )


        # ====================================================
        # PDF INDIVIDUAL MAIOR QUE O LIMITE
        # ====================================================

        if self.tamanho_atual > LIMITE_ZIP:

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
    # ABRIR PDF
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

    if total_paginas == 0:

        raise ValueError(
            "O PDF não possui páginas."
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

    paginas_transferencia = []

    paginas_transacao = []

    paginas_sem_comprovantes = []

    diagnostico = []


    # ========================================================
    # ANALISAR PÁGINA POR PÁGINA
    # ========================================================

    for indice in range(
        total_paginas
    ):

        numero_pagina = indice + 1

        progresso = (
            numero_pagina
            /
            total_paginas
        )

        progress_bar.progress(
            min(
                progresso,
                1.0
            )
        )

        status.info(
            f"🔍 Analisando página "
            f"{numero_pagina} de "
            f"{total_paginas}..."
        )

        pagina = reader.pages[
            indice
        ]


        # ====================================================
        # EXTRAIR TEXTO
        # ====================================================

        try:

            texto = (
                pagina.extract_text()
                or ""
            )

        except Exception as erro:

            texto = ""

            diagnostico.append(
                f"Página {numero_pagina}: "
                f"erro na extração do texto: "
                f"{erro}"
            )


        # ====================================================
        # IDENTIFICAR COMPROVANTE
        # ====================================================

        tipo = identificar_comprovante(
            texto
        )


        # ====================================================
        # NOME BASE
        # ====================================================

        nome_base = (
            f"pagina_{numero_pagina:04d}"
        )

        caminho_pdf_temp = os.path.join(
            pasta_temp,
            f"{nome_base}.pdf"
        )


        # ====================================================
        # COMPROVANTE
        # ====================================================

        if tipo is not None:

            criar_pdf_pagina(
                reader,
                indice,
                caminho_pdf_temp
            )

            tamanho_pdf = os.path.getsize(
                caminho_pdf_temp
            )

            nome_pdf = (
                f"{nome_base}.pdf"
            )


            # =================================================
            # PIX
            # =================================================

            if tipo == "PIX":

                quantidade_pix += 1

                paginas_pix.append(
                    numero_pagina
                )


            # =================================================
            # TRANSFERÊNCIA
            # =================================================

            elif tipo == "TRANSFERENCIA":

                quantidade_transferencia += 1

                paginas_transferencia.append(
                    numero_pagina
                )


            # =================================================
            # TRANSAÇÃO
            # =================================================

            elif tipo == "TRANSACAO_BANCARIA":

                quantidade_transacao += 1

                paginas_transacao.append(
                    numero_pagina
                )


            # =================================================
            # ADICIONAR AO ZIP
            # =================================================

            zip_comprovantes.adicionar(
                caminho_pdf_temp,
                nome_pdf,
                tamanho_pdf
            )

            total_comprovantes += 1


        # ====================================================
        # NÃO É COMPROVANTE
        # ====================================================

        else:

            paginas_sem_comprovantes.append(
                numero_pagina
            )

            criar_pdf_pagina(
                reader,
                indice,
                caminho_pdf_temp
            )

            tamanho_pdf = os.path.getsize(
                caminho_pdf_temp
            )

            nome_pdf = (
                f"{nome_base}.pdf"
            )

            zip_sem_comprovantes.adicionar(
                caminho_pdf_temp,
                nome_pdf,
                tamanho_pdf
            )

            total_sem_comprovantes += 1


        # ====================================================
        # EXCLUIR PDF TEMPORÁRIO
        # ====================================================

        try:

            os.remove(
                caminho_pdf_temp
            )

        except Exception:

            pass

        gc.collect()


    # ========================================================
    # FINALIZAR ZIPS
    # ========================================================

    status.info(
        "📦 Finalizando arquivos ZIP..."
    )

    arquivos_comprovantes = (
        zip_comprovantes.finalizar()
    )

    arquivos_sem_comprovantes = (
        zip_sem_comprovantes.finalizar()
    )


    # ========================================================
    # FECHAR LEITOR
    # ========================================================

    del reader

    gc.collect()


    # ========================================================
    # RESULTADO
    # ========================================================

    return {

        "total_paginas":
            total_paginas,

        "total_comprovantes":
            total_comprovantes,

        "total_sem_comprovantes":
            total_sem_comprovantes,

        "quantidade_pix":
            quantidade_pix,

        "quantidade_transferencia":
            quantidade_transferencia,

        "quantidade_transacao":
            quantidade_transacao,

        "paginas_pix":
            paginas_pix,

        "paginas_transferencia":
            paginas_transferencia,

        "paginas_transacao":
            paginas_transacao,

        "paginas_sem_comprovantes":
            paginas_sem_comprovantes,

        "arquivos_comprovantes":
            arquivos_comprovantes,

        "arquivos_sem_comprovantes":
            arquivos_sem_comprovantes,

        "diagnostico":
            diagnostico,

        "tempo":
            time.time() - inicio
    }


# ============================================================
# INTERFACE - UPLOAD
# ============================================================

arquivo_enviado = st.file_uploader(
    "📂 Selecione o PDF para processar",
    type=["pdf"],
    accept_multiple_files=False
)


# ============================================================
# PROCESSAMENTO
# ============================================================

if arquivo_enviado:

    st.success(
        f"📄 Arquivo selecionado: "
        f"**{arquivo_enviado.name}**"
    )

    st.write(
        f"**Tamanho:** "
        f"{formatar_tamanho(arquivo_enviado.size)}"
    )


    if st.button(
        "🚀 PROCESSAR PDF",
        type="primary",
        use_container_width=True
    ):

        pasta_trabalho = tempfile.mkdtemp(
            prefix="separador_comprovantes_"
        )


        try:

            # =================================================
            # SALVAR PDF ORIGINAL
            # =================================================

            caminho_pdf = os.path.join(
                pasta_trabalho,
                "arquivo_original.pdf"
            )

            with open(
                caminho_pdf,
                "wb"
            ) as arquivo:

                arquivo.write(
                    arquivo_enviado.getbuffer()
                )


            # =================================================
            # BARRA DE PROGRESSO
            # =================================================

            progress_bar = st.progress(
                0
            )

            status = st.empty()


            # =================================================
            # PROCESSAR
            # =================================================

            resultado = processar_pdf(

                caminho_pdf=caminho_pdf,

                pasta_trabalho=pasta_trabalho,

                progress_bar=progress_bar,

                status=status
            )


            # =================================================
            # CONCLUSÃO
            # =================================================

            progress_bar.progress(
                1.0
            )

            status.success(
                "✅ Processamento concluído!"
            )


            # =================================================
            # ESTATÍSTICAS
            # =================================================

            st.divider()

            st.subheader(
                "📊 Resultado do processamento"
            )


            col1, col2, col3, col4 = st.columns(
                4
            )


            col1.metric(
                "Total de páginas",
                resultado[
                    "total_paginas"
                ]
            )


            col2.metric(
                "Comprovantes",
                resultado[
                    "total_comprovantes"
                ]
            )


            col3.metric(
                "Sem comprovantes",
                resultado[
                    "total_sem_comprovantes"
                ]
            )


            col4.metric(
                "Tempo",
                f"{resultado['tempo']:.1f}s"
            )


            # =================================================
            # TIPOS DE COMPROVANTE
            # =================================================

            st.subheader(
                "🔎 Tipos de comprovantes"
            )


            c1, c2, c3 = st.columns(
                3
            )


            c1.metric(
                "🔵 PIX",
                resultado[
                    "quantidade_pix"
                ]
            )


            c2.metric(
                "🟢 Transferência",
                resultado[
                    "quantidade_transferencia"
                ]
            )


            c3.metric(
                "🟣 Transação bancária",
                resultado[
                    "quantidade_transacao"
                ]
            )


            # =================================================
            # ARQUIVOS ZIP
            # =================================================

            st.divider()

            st.subheader(
                "📦 Arquivos ZIP"
            )


            arquivos_zip = []

            arquivos_zip.extend(
                resultado[
                    "arquivos_comprovantes"
                ]
            )

            arquivos_zip.extend(
                resultado[
                    "arquivos_sem_comprovantes"
                ]
            )


            if arquivos_zip:

                for arquivo_zip in arquivos_zip:

                    caminho = arquivo_zip[
                        "caminho"
                    ]

                    nome = arquivo_zip[
                        "nome"
                    ]

                    tamanho = arquivo_zip[
                        "tamanho"
                    ]

                    quantidade = arquivo_zip[
                        "quantidade"
                    ]


                    st.write(
                        f"📦 **{nome}**"
                    )

                    st.write(
                        f"Arquivos: **{quantidade}** | "
                        f"Tamanho: **{formatar_tamanho(tamanho)}**"
                    )


                    with open(
                        caminho,
                        "rb"
                    ) as arquivo:

                        dados_zip = arquivo.read()


                    st.download_button(
                        label=(
                            f"⬇️ BAIXAR {nome}"
                        ),

                        data=dados_zip,

                        file_name=nome,

                        mime="application/zip",

                        key=f"download_{nome}",

                        use_container_width=True
                    )


            else:

                st.warning(
                    "Nenhum arquivo ZIP foi criado."
                )


            # =================================================
            # CONFERÊNCIA
            # =================================================

            st.divider()

            st.subheader(
                "🔎 Conferência das páginas"
            )


            with st.expander(
                "Ver páginas classificadas"
            ):

                st.write(
                    "🔵 **PIX**"
                )

                if resultado[
                    "paginas_pix"
                ]:

                    st.write(
                        resultado[
                            "paginas_pix"
                        ]
                    )

                else:

                    st.write(
                        "Nenhuma página."
                    )


                st.write(
                    "🟢 **TRANSFERÊNCIA**"
                )

                if resultado[
                    "paginas_transferencia"
                ]:

                    st.write(
                        resultado[
                            "paginas_transferencia"
                        ]
                    )

                else:

                    st.write(
                        "Nenhuma página."
                    )


                st.write(
                    "🟣 **TRANSAÇÃO BANCÁRIA**"
                )

                if resultado[
                    "paginas_transacao"
                ]:

                    st.write(
                        resultado[
                            "paginas_transacao"
                        ]
                    )

                else:

                    st.write(
                        "Nenhuma página."
                    )


                st.write(
                    "⚪ **SEM COMPROVANTE**"
                )

                if resultado[
                    "paginas_sem_comprovantes"
                ]:

                    st.write(
                        resultado[
                            "paginas_sem_comprovantes"
                        ]
                    )

                else:

                    st.write(
                        "Nenhuma página."
                    )


            # =================================================
            # DIAGNÓSTICO
            # =================================================

            if resultado[
                "diagnostico"
            ]:

                with st.expander(
                    "⚠️ Diagnóstico"
                ):

                    for mensagem in resultado[
                        "diagnostico"
                    ]:

                        st.write(
                            mensagem
                        )


        except Exception as erro:

            st.error(
                "❌ Ocorreu um erro durante "
                "o processamento."
            )

            st.exception(
                erro
            )


        finally:

            try:

                shutil.rmtree(
                    pasta_trabalho,
                    ignore_errors=True
                )

            except Exception:

                pass


# ============================================================
# RODAPÉ
# ============================================================

st.markdown(
    """
    <div class="rodape">
        Desenvolvido por <strong>Leto Milton</strong>
    </div>
    """,
    unsafe_allow_html=True
)
```
