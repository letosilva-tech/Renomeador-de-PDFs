import streamlit as st
import pandas as pd

st.set_page_config(
    page_title="Renomeador de PDFs",
    page_icon="📄",
    layout="wide"
)

st.title("📄 Renomeador de PDFs")

st.write(
    "Sistema para renomear documentos a partir de um extrato bancário."
)

st.divider()

st.header("1️⃣ Enviar extrato bancário")

arquivo_excel = st.file_uploader(
    "Selecione o arquivo Excel do extrato",
    type=["xlsx", "xls"]
)

if arquivo_excel is not None:

    st.success(f"✅ Arquivo carregado: {arquivo_excel.name}")

    try:

        df = pd.read_excel(arquivo_excel)

        st.subheader("📊 Dados encontrados no Excel")

        st.write(
            f"Quantidade de registros: **{len(df)}**"
        )

        st.dataframe(
            df,
            use_container_width=True
        )

    except Exception as erro:

        st.error(
            f"❌ Não foi possível ler o Excel: {erro}"
        )
