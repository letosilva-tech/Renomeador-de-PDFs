import streamlit as st
import pandas as pd
import re
import io
import zipfile


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
    """
    Converte qualquer valor para uma representação numérica
    simples.

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

    # Se vier como 72699.0
    texto = re.sub(r"\.0+$", "", texto)

    # Pega somente os números
    numeros = re.sub(r"\D", "", texto)

    return numeros


def extrair_op_do_nome(nome_arquivo):
    """
    Pega a primeira sequência de números do nome do PDF.

    Exemplo:

    72699-instituto-qualisa-de-gestao-ltda-000075571.pdf

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


def criar_nome_arquivo(item, nome_original):
    """
    Cria o novo nome do PDF.
    """

    item = str(item).strip()

    # Evita Item 11.0
    item = re.sub(r"\.0+$", "", item)

    return f"Item {item} - {nome_original}"


# ============================================================
# TÍTULO
# ============================================================

st.title("📄 Renomeador de PDFs")

st.write(
    "O sistema identifica a Ordem de Pagamento no início "
    "do nome do PDF e busca o Item correspondente no Excel."
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

        # Lê o Excel como texto para evitar problemas
        # de conversão automática de números
        df = pd.read_excel(
            arquivo_excel,
            dtype=str
        )

        # Remove espaços dos nomes das colunas
        df.columns = [
            str(coluna).strip()
            for coluna in df.columns
        ]

        # Verificar colunas necessárias
        coluna_op = "Ordem de Pagamento"
        coluna_item = "Item"

        if coluna_op not in df.columns:

            st.error(
                "❌ A coluna 'Ordem de Pagamento' não foi encontrada."
            )

            st.write("Colunas encontradas no Excel:")

            st.write(
                list(df.columns)
            )

            df = None

        elif coluna_item not in df.columns:

            st.error(
                "❌ A coluna 'Item' não foi encontrada."
            )

            st.write("Colunas encontradas no Excel:")

            st.write(
                list(df.columns)
            )

            df = None

        else:

            # Criar coluna auxiliar normalizada
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

            # Mostra somente as colunas importantes
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
                use_container_width=True
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
        "Selecione os PDFs que deseja renomear",
        type=["pdf"],
        accept_multiple_files=True
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


            # =================================================
            # PROCESSAR CADA PDF
            # =================================================

            for arquivo_pdf in arquivos_pdf:

                nome_original = arquivo_pdf.name

                # ---------------------------------------------
                # Extrair OP do início do nome
                # ---------------------------------------------

                numero_op = extrair_op_do_nome(
                    nome_original
                )

                # ---------------------------------------------
                # Verificar OP
                # ---------------------------------------------

                if not numero_op:

                    resultados.append({
                        "Arquivo original": nome_original,
                        "OP identificada": "",
                        "Item": "",
                        "Novo nome": "",
                        "Status": "❌ Não foi possível identificar a OP"
                    })

                    continue


                # ---------------------------------------------
                # Procurar OP no Excel
                # ---------------------------------------------

                correspondencia = df[
                    df["OP_NORMALIZADA"] == numero_op
                ]


                # ---------------------------------------------
                # OP não encontrada
                # ---------------------------------------------

                if correspondencia.empty:

                    resultados.append({
                        "Arquivo original": nome_original,
                        "OP identificada": numero_op,
                        "Item": "",
                        "Novo nome": "",
                        "Status": "⚠️ OP não encontrada no Excel"
                    })

                    continue


                # ---------------------------------------------
                # OP encontrada
                # ---------------------------------------------

                # Primeiro registro correspondente
                linha = correspondencia.iloc[0]

                item = str(
                    linha["Item"]
                ).strip()


                # ---------------------------------------------
                # Verificar Item
                # ---------------------------------------------

                if (
                    item == ""
                    or item.lower() == "nan"
                ):

                    resultados.append({
                        "Arquivo original": nome_original,
                        "OP identificada": numero_op,
                        "Item": "",
                        "Novo nome": "",
                        "Status": "⚠️ OP encontrada, mas Item está vazio"
                    })

                    continue


                # ---------------------------------------------
                # Criar novo nome
                # ---------------------------------------------

                novo_nome = criar_nome_arquivo(
                    item,
                    nome_original
                )


                # ---------------------------------------------
                # Guardar para ZIP
                # ---------------------------------------------

                arquivos_para_zip.append(
                    (
                        novo_nome,
                        arquivo_pdf.getvalue()
                    )
                )


                resultados.append({
                    "Arquivo original": nome_original,
                    "OP identificada": numero_op,
                    "Item": item,
                    "Novo nome": novo_nome,
                    "Status": "✅ Encontrado"
                })


            # =================================================
            # RESULTADOS
            # =================================================

            st.divider()

            st.header("4️⃣ Resultado do processamento")


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

            total = len(resultados)

            encontrados = sum(
                resultado["Status"] == "✅ Encontrado"
                for resultado in resultados
            )

            problemas = total - encontrados


            col1, col2, col3 = st.columns(3)


            with col1:

                st.metric(
                    "PDFs processados",
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

                    for novo_nome, conteudo in arquivos_para_zip:

                        zip_file.writestr(
                            novo_nome,
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
            # MENSAGEM FINAL
            # =================================================

            if encontrados == total:

                st.success(
                    "🎉 Todos os PDFs foram processados com sucesso!"
                )

            elif encontrados > 0:

                st.warning(
                    f"⚠️ {encontrados} PDF(s) foram processados "
                    f"e {problemas} precisam de verificação."
                )

            else:

                st.error(
                    "❌ Nenhum PDF foi relacionado ao Excel."
                )
