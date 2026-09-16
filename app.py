import streamlit as st
import pandas as pd
import io
import zipfile
import re


st.set_page_config(
    page_title="Renomeador de PDFs",
    page_icon="📄",
    layout="wide"
)


st.title("📄 Renomeador de PDFs")

st.write(
    "O sistema identifica a Ordem de Pagamento pelo nome do PDF "
    "e acrescenta o Item correspondente do Excel."
)

st.divider()


# ============================================================
# 1. EXCEL
# ============================================================

st.header("1️⃣ Enviar extrato bancário")

arquivo_excel = st.file_uploader(
    "Selecione o arquivo Excel",
    type=["xlsx", "xls"]
)


df = None


if arquivo_excel is not None:

    try:

        df = pd.read_excel(arquivo_excel)

        st.success(
            f"✅ Excel carregado: {arquivo_excel.name}"
        )

        st.write(
            f"**{len(df)} registros encontrados.**"
        )

        # Verificar colunas necessárias

        colunas_necessarias = [
            "Ordem de Pagamento",
            "Item"
        ]

        colunas_faltantes = [
            coluna
            for coluna in colunas_necessarias
            if coluna not in df.columns
        ]

        if colunas_faltantes:

            st.error(
                "❌ Não encontrei no Excel: "
                + ", ".join(colunas_faltantes)
            )

            df = None

    except Exception as erro:

        st.error(
            f"❌ Erro ao ler o Excel: {erro}"
        )

        df = None


# ============================================================
# 2. PDFS
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

        st.header("3️⃣ Processar")


        if st.button(
            "🚀 Renomear PDFs",
            type="primary"
        ):

            resultados = []


            # ------------------------------------------------
            # Preparar coluna de OP para pesquisa
            # ------------------------------------------------

            df_busca = df.copy()

            df_busca["OP_BUSCA"] = (
                df_busca["Ordem de Pagamento"]
                .astype(str)
                .str.strip()
                .str.replace(r"\.0$", "", regex=True)
            )


            # ------------------------------------------------
            # Processar cada PDF
            # ------------------------------------------------

            for arquivo_pdf in arquivos_pdf:

                nome_original = arquivo_pdf.name


                # ============================================
                # PEGAR OP DO NOME DO ARQUIVO
                # ============================================

                # Exemplo:
                #
                # 72749 - JFKAS LTDA.pdf
                #
                # resultado:
                #
                # 72749

                parte_nome = nome_original.split(" - ", 1)[0].strip()

                numero_op = parte_nome


                # ============================================
                # PROCURAR OP NO EXCEL
                # ============================================

                correspondencia = df_busca[
                    df_busca["OP_BUSCA"] == numero_op
                ]


                # ============================================
                # OP NÃO ENCONTRADA
                # ============================================

                if correspondencia.empty:

                    resultados.append({
                        "PDF original": nome_original,
                        "OP": numero_op,
                        "Item": "",
                        "Novo nome": "",
                        "Status": "⚠️ OP não encontrada no Excel"
                    })

                    continue


                # ============================================
                # PEGAR ITEM
                # ============================================

                item = correspondencia.iloc[0]["Item"]

                # Converter para texto

                item = str(item).strip()

                # Evitar que apareça "1.0"

                item = re.sub(
                    r"\.0$",
                    "",
                    item
                )


                # ============================================
                # NOVO NOME
                # ============================================

                novo_nome = (
                    f"Item {item} - {nome_original}"
                )


                resultados.append({
                    "PDF original": nome_original,
                    "OP": numero_op,
                    "Item": item,
                    "Novo nome": novo_nome,
                    "Status": "✅ Encontrado"
                })


            # =================================================
            # EXIBIR RESULTADOS
            # =================================================

            df_resultados = pd.DataFrame(resultados)


            st.divider()

            st.header("4️⃣ Resultado")


            st.dataframe(
                df_resultados,
                use_container_width=True
            )


            encontrados = sum(
                df_resultados["Status"] == "✅ Encontrado"
            )

            problemas = len(df_resultados) - encontrados


            col1, col2 = st.columns(2)


            with col1:

                st.success(
                    f"✅ {encontrados} PDF(s) prontos"
                )


            with col2:

                if problemas > 0:

                    st.warning(
                        f"⚠️ {problemas} PDF(s) com problema"
                    )

                else:

                    st.success(
                        "🎉 Todos os PDFs foram encontrados!"
                    )


            # =================================================
            # GERAR ZIP
            # =================================================

            if encontrados > 0:

                st.divider()

                st.header("5️⃣ Baixar arquivos")


                zip_buffer = io.BytesIO()


                with zipfile.ZipFile(
                    zip_buffer,
                    "w",
                    zipfile.ZIP_DEFLATED
                ) as zip_file:


                    for resultado in resultados:

                        if resultado["Status"] != "✅ Encontrado":
                            continue


                        nome_original = resultado["PDF original"]

                        novo_nome = resultado["Novo nome"]


                        arquivo_original = next(
                            (
                                arquivo
                                for arquivo in arquivos_pdf
                                if arquivo.name == nome_original
                            ),
                            None
                        )


                        if arquivo_original:

                            zip_file.writestr(
                                novo_nome,
                                arquivo_original.getvalue()
                            )


                zip_buffer.seek(0)


                st.download_button(
                    label="📦 Baixar PDFs renomeados",
                    data=zip_buffer,
                    file_name="PDFs_renomeados.zip",
                    mime="application/zip"
                )
