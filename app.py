
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
# FUNÇÕES
# ============================================================

def normalizar_valor(valor):
    """Normaliza a OP, mantendo somente os números."""
    if pd.isna(valor):
        return ""

    texto = str(valor).strip()
    texto = re.sub(r"\.0+$", "", texto)

    return re.sub(r"\D", "", texto)


def extrair_op_do_nome(nome_arquivo):
    """Extrai a OP quando ela está no início do nome do arquivo."""
    nome_sem_extensao = nome_arquivo.rsplit(".", 1)[0]

    encontrado = re.match(r"^\s*(\d+)", nome_sem_extensao)

    return encontrado.group(1) if encontrado else ""


def extrair_op_do_texto(texto):
    """Procura a Ordem de Pagamento no texto de uma página."""
    if not texto:
        return ""

    texto = re.sub(r"\s+", " ", texto)

    padroes = [
        r"ordem\s+de\s+pagamento\s*[:\-]?\s*(\d+)",
        r"\bOP\s*[:\-]?\s*(\d+)",
        r"\bO\.?\s*P\.?\s*[:\-]?\s*(\d+)",
    ]

    for padrao in padroes:
        encontrado = re.search(
            padrao,
            texto,
            flags=re.IGNORECASE
        )

        if encontrado:
            return normalizar_valor(encontrado.group(1))

    return ""


def criar_nome_arquivo(item, nome_original):
    """Cria o nome do PDF renomeado."""
    item = str(item).strip()
    item = re.sub(r"\.0+$", "", item)

    return f"Item {item} - {nome_original}"


def tamanho_mb(conteudo):
    """Retorna o tamanho em MB apenas para informação no relatório."""
    return len(conteudo) / (1024 * 1024)


def gerar_pdf_paginas(reader, paginas):
    """Gera um PDF com todas as páginas do documento identificado."""
    writer = PdfWriter()

    for indice in paginas:
        writer.add_page(reader.pages[indice])

    buffer = io.BytesIO()
    writer.write(buffer)

    return buffer.getvalue()


def identificar_documentos(reader):
    """
    Identifica documentos dentro de um PDF com vários anexos.

    Uma nova OP inicia um novo documento.
    Páginas sem OP são associadas ao documento anterior.
    Não existe divisão por tamanho.
    """
    documentos = []
    documento_atual = None

    for numero_pagina, pagina in enumerate(reader.pages):
        try:
            texto = pagina.extract_text() or ""
        except Exception:
            texto = ""

        op = extrair_op_do_texto(texto)

        if op:
            if documento_atual is not None:
                documentos.append(documento_atual)

            documento_atual = {
                "op": op,
                "paginas": [numero_pagina]
            }

        elif documento_atual is not None:
            documento_atual["paginas"].append(numero_pagina)

        else:
            # Páginas anteriores à primeira OP
            documento_atual = {
                "op": "",
                "paginas": [numero_pagina]
            }

    if documento_atual is not None:
        documentos.append(documento_atual)

    return documentos


def buscar_item(df, numero_op):
    """Localiza a OP na planilha."""
    if not numero_op:
        return None

    correspondencia = df[
        df["OP_NORMALIZADA"] == numero_op
    ]

    if correspondencia.empty:
        return None

    return correspondencia.iloc[0]


def resultado_linha(
    arquivo,
    pagina_inicial="",
    pagina_final="",
    op="",
    item="",
    tamanho="",
    novo_nome="",
    status=""
):
    """Padroniza os registros do relatório."""
    return {
        "Arquivo original": arquivo,
        "Página inicial": pagina_inicial,
        "Página final": pagina_final,
        "OP identificada": op,
        "Item": item,
        "Tamanho MB": tamanho,
        "Novo nome": novo_nome,
        "Status": status
    }


# ============================================================
# TÍTULO
# ============================================================

st.title("📄 Renomeador de PDFs")

st.write(
    """
    O sistema identifica a Ordem de Pagamento, localiza o Item
    correspondente no Excel e renomeia os documentos.

    PDFs de qualquer tamanho podem ser processados.
    Não há limite de tamanho configurado nem divisão de documentos
    por tamanho. PDFs com vários anexos são analisados para
    identificar as OPs e renomear cada documento completo.
    """
)

st.divider()


# ============================================================
# EXCEL
# ============================================================

st.header("1️⃣ Enviar extrato bancário")

arquivo_excel = st.file_uploader(
    "Selecione o arquivo Excel",
    type=["xlsx", "xls"],
    key="arquivo_excel"
)

df = None

if arquivo_excel is not None:
    try:
        df_lido = pd.read_excel(
            arquivo_excel,
            dtype=str
        )

        df_lido.columns = [
            str(coluna).strip()
            for coluna in df_lido.columns
        ]

        coluna_op = "Ordem de Pagamento"
        coluna_item = "Item"

        if coluna_op not in df_lido.columns:
            st.error(
                "❌ A coluna 'Ordem de Pagamento' não foi encontrada."
            )
            st.write(
                "Colunas encontradas:",
                list(df_lido.columns)
            )

        elif coluna_item not in df_lido.columns:
            st.error(
                "❌ A coluna 'Item' não foi encontrada."
            )
            st.write(
                "Colunas encontradas:",
                list(df_lido.columns)
            )

        else:
            df = df_lido.copy()

            df["OP_NORMALIZADA"] = (
                df[coluna_op].apply(normalizar_valor)
            )

            st.success(
                f"✅ Excel carregado: {arquivo_excel.name}"
            )

            st.write(
                f"**{len(df)} registros encontrados.**"
            )

            st.subheader("📊 Informações utilizadas")

            st.dataframe(
                df[[coluna_op, coluna_item]].copy(),
                use_container_width=True,
                hide_index=True
            )

    except Exception as erro:
        st.error(f"❌ Erro ao ler o Excel: {erro}")


# ============================================================
# SELEÇÃO DOS PDFs
# ============================================================

if df is not None:
    st.divider()
    st.header("2️⃣ Selecionar PDFs")

    arquivos_pdf = st.file_uploader(
        """
        Selecione os PDFs que deseja renomear.
        Você pode selecionar vários arquivos de uma só vez.
        """,
        type=["pdf"],
        accept_multiple_files=True,
        key="arquivos_pdf"
    )

    if arquivos_pdf:
        st.success(
            f"✅ {len(arquivos_pdf)} PDF(s) selecionado(s)"
        )

        st.divider()
        st.header("3️⃣ Processar documentos")

        if st.button(
            "🚀 Renomear PDFs",
            type="primary",
            use_container_width=True
        ):
            resultados = []
            arquivos_para_zip = []

            progresso = st.progress(0)
            total_arquivos = len(arquivos_pdf)

            # ====================================================
            # PROCESSAR CADA PDF
            # ====================================================

            for indice_arquivo, arquivo_pdf in enumerate(arquivos_pdf):
                nome_original = arquivo_pdf.name
                tamanho_original = 0

                try:
                    conteudo_original = arquivo_pdf.getvalue()
                    tamanho_original = tamanho_mb(conteudo_original)

                    reader = PdfReader(
                        io.BytesIO(conteudo_original)
                    )

                    quantidade_paginas = len(reader.pages)

                    # ------------------------------------------------
                    # IDENTIFICAR DOCUMENTOS
                    # ------------------------------------------------

                    numero_op_nome = extrair_op_do_nome(
                        nome_original
                    )

                    # Se a OP estiver no início do nome,
                    # considera o PDF inteiro como um documento.
                    if numero_op_nome:
                        documentos = [{
                            "op": numero_op_nome,
                            "paginas": list(range(quantidade_paginas))
                        }]

                    else:
                        # Caso contrário, identifica as OPs no
                        # conteúdo para reconhecer anexos diferentes.
                        documentos = identificar_documentos(reader)

                    if not documentos:
                        resultados.append(resultado_linha(
                            nome_original,
                            tamanho=round(tamanho_original, 2),
                            status="❌ Nenhuma OP identificada"
                        ))

                    else:
                        for documento in documentos:
                            numero_op = documento["op"]
                            paginas = documento["paginas"]

                            if not paginas:
                                continue

                            pagina_inicial = paginas[0] + 1
                            pagina_final = paginas[-1] + 1

                            if not numero_op:
                                resultados.append(resultado_linha(
                                    nome_original,
                                    pagina_inicial,
                                    pagina_final,
                                    tamanho=round(tamanho_original, 2),
                                    status="⚠️ Páginas sem OP identificada"
                                ))
                                continue

                            linha = buscar_item(df, numero_op)

                            if linha is None:
                                resultados.append(resultado_linha(
                                    nome_original,
                                    pagina_inicial,
                                    pagina_final,
                                    op=numero_op,
                                    tamanho=round(tamanho_original, 2),
                                    status="⚠️ OP não encontrada no Excel"
                                ))
                                continue

                            item = str(linha["Item"]).strip()

                            if item == "" or item.lower() == "nan":
                                resultados.append(resultado_linha(
                                    nome_original,
                                    pagina_inicial,
                                    pagina_final,
                                    op=numero_op,
                                    tamanho=round(tamanho_original, 2),
                                    status="⚠️ Item vazio"
                                ))
                                continue

                            # Se o documento corresponder ao PDF inteiro,
                            # mantém os bytes originais, sem reconstruí-lo.
                            if (
                                len(paginas) == quantidade_paginas
                                and paginas == list(range(quantidade_paginas))
                            ):
                                conteudo_documento = conteudo_original
                            else:
                                # Para PDFs com vários anexos, salva todas
                                # as páginas identificadas para cada OP.
                                conteudo_documento = gerar_pdf_paginas(
                                    reader,
                                    paginas
                                )

                            tamanho_documento = tamanho_mb(
                                conteudo_documento
                            )

                            # PDF renomeado sem divisão por tamanho
                            novo_nome = (
                                f"Item {item} - OP {numero_op}.pdf"
                            )

                            arquivos_para_zip.append((
                                novo_nome,
                                conteudo_documento
                            ))

                            resultados.append(resultado_linha(
                                nome_original,
                                pagina_inicial,
                                pagina_final,
                                op=numero_op,
                                item=item,
                                tamanho=round(tamanho_documento, 2),
                                novo_nome=novo_nome,
                                status="✅ Encontrado"
                            ))

                except Exception as erro:
                    resultados.append(resultado_linha(
                        nome_original,
                        tamanho=round(tamanho_original, 2),
                        status=f"❌ Erro: {erro}"
                    ))

                progresso.progress(
                    (indice_arquivo + 1) / total_arquivos
                )

            # ====================================================
            # RESULTADOS
            # ====================================================

            st.divider()
            st.header("4️⃣ Resultado do processamento")

            df_resultados = pd.DataFrame(resultados)

            st.dataframe(
                df_resultados,
                use_container_width=True,
                hide_index=True
            )

            total = len(resultados)

            encontrados = sum(
                resultado["Status"].startswith("✅ Encontrado")
                for resultado in resultados
            )

            problemas = total - encontrados

            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("Documentos processados", total)

            with col2:
                st.metric("Encontrados", encontrados)

            with col3:
                st.metric("Com problema", problemas)

            # ====================================================
            # DOWNLOAD DOS PDFs
            # ====================================================

            if arquivos_para_zip:
                st.divider()
                st.header("5️⃣ Baixar PDFs renomeados")

                zip_buffer = io.BytesIO()

                with zipfile.ZipFile(
                    zip_buffer,
                    "w",
                    zipfile.ZIP_DEFLATED
                ) as zip_file:
                    nomes_utilizados = set()

                    for novo_nome, conteudo in arquivos_para_zip:
                        nome_final = novo_nome
                        contador = 1

                        while nome_final in nomes_utilizados:
                            nome_sem_extensao = novo_nome.rsplit(".", 1)[0]

                            nome_final = (
                                f"{nome_sem_extensao} ({contador}).pdf"
                            )

                            contador += 1

                        nomes_utilizados.add(nome_final)

                        zip_file.writestr(
                            nome_final,
                            conteudo
                        )

                zip_buffer.seek(0)

                st.download_button(
                    label="📦 Baixar PDFs renomeados",
                    data=zip_buffer.getvalue(),
                    file_name="PDFs_renomeados.zip",
                    mime="application/zip",
                    use_container_width=True
                )

            # ====================================================
            # RELATÓRIO EXCEL
            # ====================================================

            if resultados:
                st.divider()
                st.header("6️⃣ Baixar relatório")

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
                    data=excel_resultado.getvalue(),
                    file_name="Resultado_processamento.xlsx",
                    mime=(
                        "application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet"
                    ),
                    use_container_width=True
                )

            # ====================================================
            # MENSAGEM FINAL
            # ====================================================

            if encontrados == total and total > 0:
                st.success(
                    "🎉 Todos os documentos foram processados com sucesso!"
                )

            elif encontrados > 0:
                st.warning(
                    f"⚠️ {encontrados} documento(s) foram processados e "
                    f"{problemas} precisam de verificação."
                )

            else:
                st.error(
                    "❌ Nenhum documento foi relacionado ao Excel."
                )


# ============================================================
# RODAPÉ - DESENVOLVEDOR
# ============================================================

st.markdown(
    """
    <div style="
        text-align: center;
        color: #808080;
        font-size: 14px;
        padding: 20px 0;
        border-top: 1px solid #e0e0e0;
        margin-top: 30px;
    ">
        Desenvolvido por <strong>Leto Milton</strong> © 2026
    </div>
    """,
    unsafe_allow_html=True
)
