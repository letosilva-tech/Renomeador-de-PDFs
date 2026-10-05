```python
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

# Limite máximo de cada PDF gerado
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

    # Remove .0 do final
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

    Aceita exemplos como:

    OP 72699
    OP: 72699
    OP - 72699
    O.P. 72699
    Ordem de Pagamento: 72699
    Ordem de Pagamento 72699
    """

    if not texto:
        return ""

    # Junta quebras de linha e espaços
    texto = re.sub(
        r"\s+",
        " ",
        texto
    )

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

    # Remove .0
    item = re.sub(
        r"\.0+$",
        "",
        item
    )

    return f"Item {item} - {nome_original}"


def tamanho_mb(conteudo):
    """
    Retorna o tamanho do conteúdo em MB.
    """

    return len(conteudo) / (
        1024 * 1024
    )


def gerar_pdf_paginas(reader, paginas):
    """
    Cria um novo PDF contendo somente as páginas informadas.

    paginas:
        lista com os índices das páginas.
    """

    writer = PdfWriter()

    for indice in paginas:

        writer.add_page(
            reader.pages[indice]
        )

    buffer = io.BytesIO()

    writer.write(buffer)

    return buffer.getvalue()


def dividir_por_tamanho(
    reader,
    paginas,
    limite_bytes=LIMITE_BYTES
):
    """
    Divide um conjunto de páginas em blocos de até 10 MB.

    Importante:
    A divisão por tamanho só acontece quando o documento
    individual ultrapassa o limite.

    O sistema tenta colocar o maior número possível
    de páginas em cada parte.
    """

    blocos = []

    bloco_atual = []

    for pagina in paginas:

        teste = bloco_atual + [
            pagina
        ]

        conteudo_teste = gerar_pdf_paginas(
            reader,
            teste
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

            # Salva o bloco anterior
            if bloco_atual:

                conteudo_bloco = (
                    gerar_pdf_paginas(
                        reader,
                        bloco_atual
                    )
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

                # Uma única página já ultrapassa 10 MB
                conteudo_pagina = (
                    gerar_pdf_paginas(
                        reader,
                        [pagina]
                    )
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

        conteudo_bloco = (
            gerar_pdf_paginas(
                reader,
                bloco_atual
            )
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
    Analisa o PDF página por página.

    Uma nova OP encontrada indica o início
    de um novo documento/anexo.

    Exemplo:

        Página 1 -> OP 72699
        Página 2 -> sem OP
        Página 3 -> sem OP
        Página 4 -> OP 72700
        Página 5 -> sem OP

    Resultado:

        OP 72699 -> páginas 1,2,3
        OP 72700 -> páginas 4,5
    """

    documentos = []

    documento_atual = None

    for numero_pagina, pagina in enumerate(
        reader.pages
    ):

        try:

            texto = (
                pagina.extract_text()
                or ""
            )

        except Exception:

            texto = ""

        op = extrair_op_do_texto(
            texto
        )

        # ----------------------------------------------------
        # Encontrou nova OP
        # ----------------------------------------------------

        if op:

            # Fecha documento anterior
            if documento_atual is not None:

                documentos.append(
                    documento_atual
                )

            # Inicia novo documento
            documento_atual = {
                "op": op,
                "paginas": [
                    numero_pagina
                ]
            }

        else:

            # Continua documento anterior
            if documento_atual is not None:

                documento_atual[
                    "paginas"
                ].append(
                    numero_pagina
                )

            else:

                # Página antes da primeira OP
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


def buscar_item(df, numero_op):
    """
    Procura a OP no Excel.
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

st.title(
    "📄 Renomeador de PDFs"
)

st.write(
    """
    O sistema identifica a Ordem de Pagamento,
    localiza o Item correspondente no Excel
    e renomeia os documentos.

    Para PDFs grandes com vários anexos,
    o sistema identifica cada documento pela OP
    encontrada no conteúdo do PDF.
    """
)

st.divider()


# ============================================================
# EXCEL
# ============================================================

st.header(
    "1️⃣ Enviar extrato bancário"
)

arquivo_excel = st.file_uploader(
    "Selecione o arquivo Excel",
    type=[
        "xlsx",
        "xls"
    ]
)

df = None


if arquivo_excel is not None:

    try:

        # ----------------------------------------------------
        # Ler Excel como texto
        # ----------------------------------------------------

        df = pd.read_excel(
            arquivo_excel,
            dtype=str
        )

        # ----------------------------------------------------
        # Limpar nomes das colunas
        # ----------------------------------------------------

        df.columns = [
            str(coluna).strip()
            for coluna in df.columns
        ]

        coluna_op = (
            "Ordem de Pagamento"
        )

        coluna_item = "Item"

        # ----------------------------------------------------
        # Verificar coluna OP
        # ----------------------------------------------------

        if coluna_op not in df.columns:

            st.error(
                "❌ A coluna "
                "'Ordem de Pagamento' "
                "não foi encontrada."
            )

            st.write(
                "Colunas encontradas:"
            )

            st.write(
                list(df.columns)
            )

            df = None

        # ----------------------------------------------------
        # Verificar coluna Item
        # ----------------------------------------------------

        elif coluna_item not in df.columns:

            st.error(
                "❌ A coluna 'Item' "
                "não foi encontrada."
            )

            st.write(
                "Colunas encontradas:"
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
                f"✅ Excel carregado: "
                f"{arquivo_excel.name}"
            )

            st.write(
                f"**{len(df)} registros encontrados.**"
            )

            # ------------------------------------------------
            # Mostrar dados
            # ------------------------------------------------

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

    st.header(
        "2️⃣ Selecionar PDFs"
    )

    arquivos_pdf = st.file_uploader(
        """
        Selecione os PDFs que deseja renomear.

        PDFs grandes contendo vários anexos
        também podem ser processados.
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

                nome_original = (
                    arquivo_pdf.name
                )

                try:

                    # -----------------------------------------
                    # Ler arquivo
                    # -----------------------------------------

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

                    # =================================================
                    # PDF ATÉ 10 MB
                    # =================================================

                    if len(
                        conteudo_original
                    ) <= LIMITE_BYTES:

                        # ---------------------------------------------
                        # OP pelo nome
                        # ---------------------------------------------

                        numero_op = (
                            extrair_op_do_nome(
                                nome_original
                            )
                        )

                        # ---------------------------------------------
                        # Se não encontrou no nome,
                        # procura na primeira página
                        # ---------------------------------------------

                        if not numero_op:

                            try:

                                texto = (
                                    reader.pages[0]
                                    .extract_text()
                                    or ""
                                )

                                numero_op = (
                                    extrair_op_do_texto(
                                        texto
                                    )
                                )

                            except Exception:

                                numero_op = ""

                        # ---------------------------------------------
                        # OP não identificada
                        # ---------------------------------------------

                        if not numero_op:

                            resultados.append({

                                "Arquivo original":
                                    nome_original,

                                "Página inicial":
                                    1,

                                "Página final":
                                    quantidade_paginas,

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
                                    "❌ Não foi possível identificar a OP"
                            })

                        else:

                            # -----------------------------------------
                            # Buscar OP no Excel
                            # -----------------------------------------

                            linha = buscar_item(
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

                                # -------------------------------------
                                # Item vazio
                                # -------------------------------------

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
                                            "⚠️ OP encontrada, mas Item está vazio"
                                    })

                                else:

                                    # ---------------------------------
                                    # Nome final
                                    # ---------------------------------

                                    novo_nome = (
                                        criar_nome_arquivo(
                                            item,
                                            nome_original
                                        )
                                    )

                                    # ---------------------------------
                                    # Adicionar ZIP
                                    # ---------------------------------

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

                    # =================================================
                    # PDF ACIMA DE 10 MB
                    # =================================================

                    else:

                        st.info(
                            f"📄 PDF grande identificado: "
                            f"{nome_original} "
                            f"({tamanho_original:.2f} MB)"
                        )

                        # ---------------------------------------------
                        # Identificar documentos
                        # ---------------------------------------------

                        documentos = (
                            identificar_documentos(
                                reader
                            )
                        )

                        # ---------------------------------------------
                        # Nenhum documento
                        # ---------------------------------------------

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
                                    "❌ Nenhuma OP identificada"
                            })

                        # ---------------------------------------------
                        # Processar documentos encontrados
                        # ---------------------------------------------

                        else:

                            for documento in documentos:

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

                                # -------------------------------------
                                # Documento sem OP
                                # -------------------------------------

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
                                            "⚠️ Páginas sem OP identificada"
                                    })

                                    continue

                                # -------------------------------------
                                # Buscar Item
                                # -------------------------------------

                                linha = buscar_item(
                                    df,
                                    numero_op
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

                                # -------------------------------------
                                # Item vazio
                                # -------------------------------------

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

                                # -------------------------------------
                                # Dividir somente se passar de 10 MB
                                # -------------------------------------

                                blocos = (
                                    dividir_por_tamanho(
                                        reader,
                                        paginas
                                    )
                                )

                                total_blocos = len(
                                    blocos
                                )

                                # -------------------------------------
                                # Processar blocos
                                # -------------------------------------

                                for numero_bloco, (
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

                                    pagina_inicio = (
                                        paginas_bloco[0]
                                        + 1
                                    )

                                    pagina_fim = (
                                        paginas_bloco[-1]
                                        + 1
                                    )

                                    # ---------------------------------
                                    # Criar nome
                                    # ---------------------------------

                                    if total_blocos == 1:

                                        novo_nome = (
                                            f"Item {item} - "
                                            f"OP {numero_op}.pdf"
                                        )

                                    else:

                                        novo_nome = (
                                            f"Item {item} - "
                                            f"OP {numero_op} - "
                                            f"Parte {numero_bloco}.pdf"
                                        )

                                    # ---------------------------------
                                    # Uma página maior que 10 MB
                                    # ---------------------------------

                                    if (
                                        tamanho_bloco
                                        > LIMITE_MB
                                    ):

                                        resultados.append({

                                            "Arquivo original":
                                                nome_original,

                                            "Página inicial":
                                                pagina_inicio,

                                            "Página final":
                                                pagina_fim,

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
                                                "❌ Uma página excede 10 MB"
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
                                                pagina_inicio,

                                            "Página final":
                                                pagina_fim,

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
                # Atualizar barra
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
                total - encontrados
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

                    nomes_utilizados = set()

                    for (
                        novo_nome,
                        conteudo
                    ) in arquivos_para_zip:

                        nome_final = (
                            novo_nome
                        )

                        contador = 1

                        # -----------------------------------------
                        # Evita nomes duplicados
                        # -----------------------------------------

                        while (
                            nome_final
                            in nomes_utilizados
                        ):

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

                        nomes_utilizados.add(
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
            # RELATÓRIO EXCEL
            # =================================================

            if resultados:

                st.divider()

                st.header(
                    "6️⃣ Baixar relatório"
                )

                excel_resultado = (
                    io.BytesIO()
                )

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
                    "🎉 Todos os documentos foram "
                    "processados com sucesso!"
                )

            elif encontrados > 0:

                st.warning(
                    f"⚠️ {encontrados} documento(s) "
                    f"foram processados e "
                    f"{problemas} precisam de verificação."
                )

            else:

                st.error(
                    "❌ Nenhum documento foi relacionado "
                    "ao Excel."
                )
```

### 2. `requirements.txt`

Crie também este arquivo:

```text
streamlit
pandas
openpyxl
xlrd
pypdf
```

### 3. Configuração para arquivos grandes

Na mesma pasta do `app.py`, crie:

```text
.streamlit/
└── config.toml
```

E coloque:

```toml
[server]
maxUploadSize = 2000
```

Assim o Streamlit poderá receber arquivos de até aproximadamente **2 GB**.

### O que essa versão faz

Se você enviar um arquivo como:

```text
arquivo_grande.pdf
```

com, por exemplo, 300 MB:

```text
Página 1  → OP 72699
Página 2
Página 3
Página 4
Página 5  → OP 72700
Página 6
Página 7
Página 8  → OP 72701
...
```

ele tentará montar:

```text
OP 72699
├── páginas 1–4

OP 72700
├── páginas 5–7

OP 72701
├── páginas 8–...
```

Depois consulta o Excel:

```text
Ordem de Pagamento | Item
72699              | 15
72700              | 18
72701              | 22
```

E gera:

```text
Item 15 - OP 72699.pdf
Item 18 - OP 72700.pdf
Item 22 - OP 72701.pdf
```

Se um único anexo tiver mais de 10 MB:

```text
Item 15 - OP 72699 - Parte 1.pdf
Item 15 - OP 72699 - Parte 2.pdf
Item 15 - OP 72699 - Parte 3.pdf
```

**Atenção:** para o agrupamento automático funcionar, a OP precisa estar no **texto pesquisável das páginas**. Se o seu PDF grande for um documento escaneado/imagem, essa versão não conseguirá enxergar a OP sem OCR. Nesse caso, a solução precisa incorporar OCR.
