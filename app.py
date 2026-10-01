import streamlit as st
import pandas as pd
import re
import io
import zipfile

from pypdf import PdfReader, PdfWriter


# ============================================================
# CONFIGURAÇÃO
# ============================================================

st.set_page_config(
    page_title="Renomeador de PDFs",
    page_icon="📄",
    layout="wide"
)


# ============================================================
# CONFIGURAÇÕES DO SISTEMA
# ============================================================

LIMITE_MB = 10
LIMITE_BYTES = LIMITE_MB * 1024 * 1024


# ============================================================
# FUNÇÕES
# ============================================================

def normalizar_valor(valor):
    """
    Converte qualquer valor para uma representação numérica simples.

    Exemplos:

    72699       -> 72699
    72699.0     -> 72699
    "72699"     -> 72699
    " 72699 "   -> 72699
    "OP 72699"  -> 72699
    """

    if pd.isna(valor):
        return ""

    texto = str(valor).strip()

    # Remove .0 no final
    texto = re.sub(r"\.0+$", "", texto)

    # Mantém somente números
    numeros = re.sub(r"\D", "", texto)

    return numeros


def extrair_op_do_nome(nome_arquivo):
    """
    Pega a primeira sequência de números do nome do PDF.

    Exemplo:

    72699-instituto-qualisa-de-gestao-ltda.pdf

    retorna:

    72699
    """

    nome_sem_extensao = nome_arquivo.rsplit(".", 1)[0]

    encontrado = re.match(
        r"^\s*(\d+)",
        nome_sem_extensao
    )

    if encontrado:
        return encontrado.group(1)

    return ""


def extrair_op_do_texto(texto):
    """
    Procura uma Ordem de Pagamento dentro do texto da página.

    Aceita formatos como:

    OP 72699
    OP: 72699
    Ordem de Pagamento: 72699
    Ordem de Pagamento 72699

    Também procura padrões próximos a 'OP'.
    """

    if not texto:
        return ""

    # Normaliza espaços
    texto = re.sub(r"\s+", " ", texto)

    padroes = [

        # Ordem de Pagamento: 72699
        r"ordem\s+de\s+pagamento\s*[:\-]?\s*(\d+)",

        # OP: 72699
        r"\bOP\s*[:\-]?\s*(\d+)",

        # O.P.: 72699
        r"\bO\.?\s*P\.?\s*[:\-]?\s*(\d+)",
    ]

    for padrao in padroes:

        encontrado = re.search(
            padrao,
            texto,
            flags=re.IGNORECASE
        )

        if encontrado:

            return normalizar_valor(
                encontrado.group(1)
            )

    return ""


def criar_nome_arquivo(item, nome_original):
    """
    Cria o novo nome do PDF.
    """

    item = str(item).strip()

    # Evita Item 11.0
    item = re.sub(r"\.0+$", "", item)

    return f"Item {item} - {nome_original}"


def tamanho_mb(conteudo):
    """
    Retorna tamanho em MB.
    """

    return len(conteudo) / (1024 * 1024)


def gerar_pdf_paginas(reader, paginas):
    """
    Cria um novo PDF contendo as páginas informadas.

    paginas = lista de índices das páginas.
    """

    writer = PdfWriter()

    for indice in paginas:

        writer.add_page(
            reader.pages[indice]
        )

    buffer = io.BytesIO()

    writer.write(buffer)

    return buffer.getvalue()


def dividir_documento_por_tamanho(
    reader,
    paginas,
    limite_bytes=LIMITE_BYTES
):
    """
    Divide um documento SOMENTE se ele ultrapassar o limite.

    A divisão tenta agrupar o maior número possível de páginas
    sem ultrapassar 10 MB.

    Retorna uma lista de blocos.
    """

    blocos = []

    bloco_atual = []

    for pagina in paginas:

        teste_paginas = bloco_atual + [pagina]

        conteudo_teste = gerar_pdf_paginas(
            reader,
            teste_paginas
        )

        tamanho_teste = len(
            conteudo_teste
        )

        # Ainda cabe no limite
        if tamanho_teste <= limite_bytes:

            bloco_atual.append(
                pagina
            )

        else:

            # Se já existe algo no bloco,
            # salva o bloco atual
            if bloco_atual:

                conteudo_bloco = gerar_pdf_paginas(
                    reader,
                    bloco_atual
                )

                blocos.append(
                    (
                        bloco_atual.copy(),
                        conteudo_bloco
                    )
                )

                bloco_atual = [
                    pagina
                ]

            else:

                # Página individual maior que 10 MB
                conteudo_pagina = gerar_pdf_paginas(
                    reader,
                    [pagina]
                )

                blocos.append(
                    (
                        [pagina],
                        conteudo_pagina
                    )
                )

                bloco_atual = []

    # Último bloco
    if bloco_atual:

        conteudo_bloco = gerar_pdf_paginas(
            reader,
            bloco_atual
        )

        blocos.append(
            (
                bloco_atual.copy(),
                conteudo_bloco
            )
        )

    return blocos


def identificar_documentos(reader):
    """
    Analisa página por página e tenta identificar
    onde começa cada documento.

    A regra principal é:

    Uma nova OP encontrada em uma página
    indica o início de um novo documento.

    Retorna:

    [
        {
            "op": "72699",
            "paginas": [0,1,2]
        },
        ...
    ]
    """

    documentos = []

    documento_atual = None

    for numero_pagina, pagina in enumerate(
        reader.pages
    ):

        try:

            texto = pagina.extract_text() or ""

        except Exception:

            texto = ""

        op = extrair_op_do_texto(
            texto
        )

        # ----------------------------------------------------
        # Encontrou uma nova OP
        # ----------------------------------------------------

        if op:

            # Se já existe documento aberto,
            # fecha o anterior
            if documento_atual is not None:

                documentos.append(
                    documento_atual
                )

            documento_atual = {
                "op": op,
                "paginas": [
                    numero_pagina
                ]
            }

        else:

            # Página continua pertencendo ao
            # documento anterior
            if documento_atual is not None:

                documento_atual[
                    "paginas"
                ].append(
                    numero_pagina
                )

            else:

                # Ainda não encontramos uma OP.
                # Criamos um documento sem OP.
                documento_atual = {
                    "op": "",
                    "paginas": [
                        numero_pagina
                    ]
                }

    # Fecha último documento
    if documento_atual is not None:

        documentos.append(
            documento_atual
        )

    return documentos


def buscar_item_por_op(
    df,
    numero_op
):
    """
    Procura o Item correspondente à OP.
    """

    if not numero_op:
        return None

    correspondencia = df[
        df["OP_NORMALIZADA"] == numero_op
    ]

    if correspondencia.empty:

        return None

    return correspondencia.iloc[0]


# ============================================================
# TÍTULO
# ============================================================

st.title("📄 Renomeador de PDFs")

st.write(
    """
    O sistema identifica a Ordem de Pagamento, localiza o Item
    correspondente no Excel e renomeia os documentos.

    Quando o PDF possui vários anexos, o sistema tenta identificar
    o início de cada documento pela OP encontrada no conteúdo.
    """
)

st.divider()


# ============================================================
# EXCEL
# ============================================================

st.header("1️⃣ Enviar extrato bancário")

arquivo_excel = st.file_uploader(
    "Selecione o arquivo Excel",
    type=["xlsx", "xls"]
)


df = None


if arquivo_excel is not None:

    try:

        df = pd.read_excel(
            arquivo_excel,
            dtype=str
        )

        # Remove espaços dos nomes das colunas
        df.columns = [
            str(coluna).strip()
            for coluna in df.columns
        ]

        coluna_op = "Ordem de Pagamento"
        coluna_item = "Item"

        # ----------------------------------------------------
        # Verificar OP
        # ----------------------------------------------------

        if coluna_op not in df.columns:

            st.error(
                "❌ A coluna 'Ordem de Pagamento' não foi encontrada."
            )

            st.write(
                "Colunas encontradas no Excel:"
            )

            st.write(
                list(df.columns)
            )

            df = None

        # ----------------------------------------------------
        # Verificar Item
        # ----------------------------------------------------

        elif coluna_item not in df.columns:

            st.error(
                "❌ A coluna 'Item' não foi encontrada."
            )

            st.write(
                "Colunas encontradas no Excel:"
            )

            st.write(
                list(df.columns)
            )

            df = None

        else:

            # ------------------------------------------------
            # Normalizar OP
            # ------------------------------------------------

            df["OP_NORMALIZADA"] = (
                df[coluna_op]
                .apply(normalizar_valor)
            )

            st.success(
                f"✅ Excel carregado: {arquivo_excel.name}"
            )

            st.write(
                f"**{len(df)} registros encontrados.**"
            )

            st.subheader(
                "📊 Informações utilizadas"
            )

            visualizacao = df[
                [
                    coluna_op,
                    coluna_item
                ]
            ].copy()

            st.dataframe(
                visualizacao,
                use_container_width=True,
                hide_index=True
            )

    except Exception as erro:

        st.error(
            f"❌ Erro ao ler o Excel: {erro}"
        )

        df = None


# ============================================================
# PDFS
# ============================================================

if df is not None:

    st.divider()

    st.header("2️⃣ Selecionar PDFs")

    arquivos_pdf = st.file_uploader(
        """
        Selecione os PDFs.

        PDFs grandes contendo vários documentos serão analisados
        página por página para identificar as OPs.
        """,
        type=["pdf"],
        accept_multiple_files=True
    )

    if arquivos_pdf:

        st.success(
            f"✅ {len(arquivos_pdf)} PDF(s) selecionado(s)"
        )

        st.divider()

        st.header(
            "3️⃣ Processar documentos"
        )

        if st.button(
            "🚀 Renomear PDFs",
            type="primary",
            use_container_width=True
        ):

            resultados = []

            arquivos_para_zip = []

            progresso = st.progress(
                0
            )

            total_arquivos = len(
                arquivos_pdf
            )

            # =================================================
            # PROCESSAR CADA PDF
            # =================================================

            for indice_arquivo, arquivo_pdf in enumerate(
                arquivos_pdf
            ):

                nome_original = arquivo_pdf.name

                try:

                    conteudo_original = (
                        arquivo_pdf.getvalue()
                    )

                    tamanho_original = (
                        tamanho_mb(
                            conteudo_original
                        )
                    )

                    # -----------------------------------------
                    # Ler PDF
                    # -----------------------------------------

                    reader = PdfReader(
                        io.BytesIO(
                            conteudo_original
                        )
                    )

                    quantidade_paginas = len(
                        reader.pages
                    )

                    # -----------------------------------------
                    # PDF pequeno
                    # -----------------------------------------

                    if (
                        len(conteudo_original)
                        <= LIMITE_BYTES
                    ):

                        # Primeiro tenta OP no nome
                        numero_op = (
                            extrair_op_do_nome(
                                nome_original
                            )
                        )

                        # Se não encontrou no nome,
                        # procura na primeira página
                        if not numero_op:

                            try:

                                texto_primeira_pagina = (
                                    reader.pages[0]
                                    .extract_text()
                                    or ""
                                )

                                numero_op = (
                                    extrair_op_do_texto(
                                        texto_primeira_pagina
                                    )
                                )

                            except Exception:

                                numero_op = ""

                        # -------------------------------------
                        # Procurar OP no Excel
                        # -------------------------------------

                        linha = buscar_item_por_op(
                            df,
                            numero_op
                        )

                        if linha is None:

                            resultados.append({

                                "Arquivo original":
                                    nome_original,

                                "Página inicial":
                                    1,

                                "Página final":
                                    quantidade_paginas,

                                "OP identificada":
                                    numero_op,

                                "Item":
                                    "",

                                "Tamanho MB":
                                    round(
                                        tamanho_original,
                                        2
                                    ),

                                "Novo nome":
                                    "",

                                "Status":
                                    "⚠️ OP não encontrada no Excel"
                            })

                        else:

                            item = str(
                                linha["Item"]
                            ).strip()

                            if (
                                item == ""
                                or item.lower()
                                == "nan"
                            ):

                                resultados.append({

                                    "Arquivo original":
                                        nome_original,

                                    "Página inicial":
                                        1,

                                    "Página final":
                                        quantidade_paginas,

                                    "OP identificada":
                                        numero_op,

                                    "Item":
                                        "",

                                    "Tamanho MB":
                                        round(
                                            tamanho_original,
                                            2
                                        ),

                                    "Novo nome":
                                        "",

                                    "Status":
                                        "⚠️ Item vazio"
                                })

                            else:

                                novo_nome = (
                                    criar_nome_arquivo(
                                        item,
                                        nome_original
                                    )
                                )

                                arquivos_para_zip.append(
                                    (
                                        novo_nome,
                                        conteudo_original
                                    )
                                )

                                resultados.append({

                                    "Arquivo original":
                                        nome_original,

                                    "Página inicial":
                                        1,

                                    "Página final":
                                        quantidade_paginas,

                                    "OP identificada":
                                        numero_op,

                                    "Item":
                                        item,

                                    "Tamanho MB":
                                        round(
                                            tamanho_original,
                                            2
                                        ),

                                    "Novo nome":
                                        novo_nome,

                                    "Status":
                                        "✅ Encontrado"
                                })

                    # -----------------------------------------
                    # PDF grande
                    # -----------------------------------------

                    else:

                        st.info(
                            f"📄 Analisando PDF grande: "
                            f"{nome_original} "
                            f"({tamanho_original:.2f} MB)"
                        )

                        documentos = (
                            identificar_documentos(
                                reader
                            )
                        )

                        # -------------------------------------
                        # Nenhuma OP identificada
                        # -------------------------------------

                        if not documentos:

                            resultados.append({

                                "Arquivo original":
                                    nome_original,

                                "Página inicial":
                                    "",

                                "Página final":
                                    "",

                                "OP identificada":
                                    "",

                                "Item":
                                    "",

                                "Tamanho MB":
                                    round(
                                        tamanho_original,
                                        2
                                    ),

                                "Novo nome":
                                    "",

                                "Status":
                                    "❌ Nenhum documento identificado"
                            })

                        else:

                            contador_documento = 0

                            for documento in documentos:

                                contador_documento += 1

                                numero_op = (
                                    documento["op"]
                                )

                                paginas = (
                                    documento["paginas"]
                                )

                                pagina_inicial = (
                                    paginas[0] + 1
                                )

                                pagina_final = (
                                    paginas[-1] + 1
                                )

                                # ---------------------------------
                                # Documento sem OP
                                # ---------------------------------

                                if not numero_op:

                                    resultados.append({

                                        "Arquivo original":
                                            nome_original,

                                        "Página inicial":
                                            pagina_inicial,

                                        "Página final":
                                            pagina_final,

                                        "OP identificada":
                                            "",

                                        "Item":
                                            "",

                                        "Tamanho MB":
                                            "",

                                        "Novo nome":
                                            "",

                                        "Status":
                                            "⚠️ Documento sem OP identificada"
                                    })

                                    continue

                                # ---------------------------------
                                # Buscar Item
                                # ---------------------------------

                                linha = (
                                    buscar_item_por_op(
                                        df,
                                        numero_op
                                    )
                                )

                                if linha is None:

                                    resultados.append({

                                        "Arquivo original":
                                            nome_original,

                                        "Página inicial":
                                            pagina_inicial,

                                        "Página final":
                                            pagina_final,

                                        "OP identificada":
                                            numero_op,

                                        "Item":
                                            "",

                                        "Tamanho MB":
                                            "",

                                        "Novo nome":
                                            "",

                                        "Status":
                                            "⚠️ OP não encontrada no Excel"
                                    })

                                    continue

                                item = str(
                                    linha["Item"]
                                ).strip()

                                if (
                                    item == ""
                                    or item.lower()
                                    == "nan"
                                ):

                                    resultados.append({

                                        "Arquivo original":
                                            nome_original,

                                        "Página inicial":
                                            pagina_inicial,

                                        "Página final":
                                            pagina_final,

                                        "OP identificada":
                                            numero_op,

                                        "Item":
                                            "",

                                        "Tamanho MB":
                                            "",

                                        "Novo nome":
                                            "",

                                        "Status":
                                            "⚠️ Item vazio"
                                    })

                                    continue

                                # ---------------------------------
                                # Gerar documento
                                # ---------------------------------

                                blocos = (
                                    dividir_documento_por_tamanho(
                                        reader,
                                        paginas
                                    )
                                )

                                quantidade_blocos = len(
                                    blocos
                                )

                                # ---------------------------------
                                # Cada bloco
                                # ---------------------------------

                                for indice_bloco, (
                                    paginas_bloco,
                                    conteudo_bloco
                                ) in enumerate(
                                    blocos,
                                    start=1
                                ):

                                    tamanho_bloco = (
                                        tamanho_mb(
                                            conteudo_bloco
                                        )
                                    )

                                    pagina_inicio_bloco = (
                                        paginas_bloco[0]
                                        + 1
                                    )

                                    pagina_fim_bloco = (
                                        paginas_bloco[-1]
                                        + 1
                                    )

                                    # -----------------------------
                                    # Nome
                                    # -----------------------------

                                    if quantidade_blocos == 1:

                                        novo_nome = (
                                            f"Item {item} - "
                                            f"OP {numero_op}.pdf"
                                        )

                                    else:

                                        novo_nome = (
                                            f"Item {item} - "
                                            f"OP {numero_op} - "
                                            f"Parte {indice_bloco}.pdf"
                                        )

                                    # -----------------------------
                                    # Documento acima de 10 MB
                                    # -----------------------------

                                    if (
                                        tamanho_bloco
                                        > LIMITE_MB
                                    ):

                                        resultados.append({

                                            "Arquivo original":
                                                nome_original,

                                            "Página inicial":
                                                pagina_inicio_bloco,

                                            "Página final":
                                                pagina_fim_bloco,

                                            "OP identificada":
                                                numero_op,

                                            "Item":
                                                item,

                                            "Tamanho MB":
                                                round(
                                                    tamanho_bloco,
                                                    2
                                                ),

                                            "Novo nome":
                                                novo_nome,

                                            "Status":
                                                "❌ Página individual excede 10 MB"
                                        })

                                    else:

                                        arquivos_para_zip.append(
                                            (
                                                novo_nome,
                                                conteudo_bloco
                                            )
                                        )

                                        resultados.append({

                                            "Arquivo original":
                                                nome_original,

                                            "Página inicial":
                                                pagina_inicio_bloco,

                                            "Página final":
                                                pagina_fim_bloco,

                                            "OP identificada":
                                                numero_op,

                                            "Item":
                                                item,

                                            "Tamanho MB":
                                                round(
                                                    tamanho_bloco,
                                                    2
                                                ),

                                            "Novo nome":
                                                novo_nome,

                                            "Status":
                                                "✅ Encontrado"
                                        })

                except Exception as erro:

                    resultados.append({

                        "Arquivo original":
                            nome_original,

                        "Página inicial":
                            "",

                        "Página final":
                            "",

                        "OP identificada":
                            "",

                        "Item":
                            "",

                        "Tamanho MB":
                            round(
                                tamanho_original
                                if "tamanho_original"
                                in locals()
                                else 0,
                                2
                            ),

                        "Novo nome":
                            "",

                        "Status":
                            f"❌ Erro: {erro}"
                    })

                # ---------------------------------------------
                # Atualizar progresso
                # ---------------------------------------------

                progresso.progress(
                    (indice_arquivo + 1)
                    / total_arquivos
                )

            # =================================================
            # RESULTADOS
            # =================================================

            st.divider()

            st.header(
                "4️⃣ Resultado do processamento"
            )

            df_resultados = pd.DataFrame(
                resultados
            )

            st.dataframe(
                df_resultados,
                use_container_width=True,
                hide_index=True
            )

            # =================================================
            # RESUMO
            # =================================================

            total = len(
                resultados
            )

            encontrados = sum(
                resultado["Status"]
                == "✅ Encontrado"
                for resultado in resultados
            )

            problemas = (
                total
                - encontrados
            )

            col1, col2, col3 = st.columns(
                3
            )

            with col1:

                st.metric(
                    "Documentos processados",
                    total
                )

            with col2:

                st.metric(
                    "Encontrados",
                    encontrados
                )

            with col3:

                st.metric(
                    "Com problema",
                    problemas
                )

            # =================================================
            # ZIP
            # =================================================

            if arquivos_para_zip:

                st.divider()

                st.header(
                    "5️⃣ Baixar PDFs renomeados"
                )

                zip_buffer = io.BytesIO()

                with zipfile.ZipFile(
                    zip_buffer,
                    "w",
                    zipfile.ZIP_DEFLATED
                ) as zip_file:

                    nomes_zip = set()

                    for (
                        novo_nome,
                        conteudo
                    ) in arquivos_para_zip:

                        # -------------------------------------
                        # Evita arquivos com mesmo nome
                        # -------------------------------------

                        nome_final = novo_nome

                        contador = 1

                        while nome_final in nomes_zip:

                            nome_sem_extensao = (
                                novo_nome
                                .rsplit(
                                    ".",
                                    1
                                )[0]
                            )

                            nome_final = (
                                f"{nome_sem_extensao} "
                                f"({contador}).pdf"
                            )

                            contador += 1

                        nomes_zip.add(
                            nome_final
                        )

                        zip_file.writestr(
                            nome_final,
                            conteudo
                        )

                zip_buffer.seek(0)

                st.download_button(
                    label="📦 Baixar PDFs renomeados",
                    data=zip_buffer,
                    file_name="PDFs_renomeados.zip",
                    mime="application/zip",
                    use_container_width=True
                )

            # =================================================
            # EXPORTAR RESULTADO
            # =================================================

            if resultados:

                st.divider()

                st.header(
                    "6️⃣ Baixar relatório"
                )

                excel_resultado = io.BytesIO()

                with pd.ExcelWriter(
                    excel_resultado,
                    engine="openpyxl"
                ) as writer:

                    df_resultados.to_excel(
                        writer,
                        index=False,
                        sheet_name="Resultado"
                    )

                excel_resultado.seek(0)

                st.download_button(
                    label="📊 Baixar relatório Excel",
                    data=excel_resultado,
                    file_name="Resultado_processamento.xlsx",
                    mime=(
                        "application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet"
                    ),
                    use_container_width=True
                )

            # =================================================
            # MENSAGEM FINAL
            # =================================================

            if encontrados == total:

                st.success(
                    "🎉 Todos os documentos foram processados "
                    "com sucesso!"
                )

            elif encontrados > 0:

                st.warning(
                    f"⚠️ {encontrados} documento(s) foram "
                    f"processados e {problemas} precisam "
                    f"de verificação."
                )

            else:

                st.error(
                    "❌ Nenhum documento foi relacionado "
                    "ao Excel."
                )
