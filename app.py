import streamlit as st
import os
import re
import unicodedata
import tempfile
import shutil
import gc
import zipfile
from io import BytesIO

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

# Usamos 9,5 MB para deixar margem para o ZIP não ultrapassar

# 10 MB devido aos metadados internos do arquivo ZIP.

LIMITE_MB = 9.5

LIMITE_BYTES = int(
LIMITE_MB * 1024 * 1024
)

# ============================================================

# TÍTULO

# ============================================================

st.title(
"📄 Separador de Comprovantes"
)

st.write(
"""
Envie um PDF contendo vários documentos.

```
O sistema irá identificar os comprovantes e separar:

🔵 **COMPROVANTE PIX**

🟢 **COMPROVANTE DE TRANSFERENCIA**

🟣 **COMPROVANTE DE TRANSACAO BANCARIA**

As páginas restantes serão colocadas separadamente.
"""
```

)

st.info(
"""
📦 Os comprovantes não serão gerados um por um.

```
O sistema irá juntar vários comprovantes em arquivos PDF
maiores e depois colocar esses PDFs em ZIPs de até
aproximadamente 9,5 MB.
"""
```

)

# ============================================================

# NORMALIZA TEXTO

# ============================================================

def normalizar_texto(texto):

```
if not texto:
    return ""

# Remove acentos
texto = unicodedata.normalize(
    "NFKD",
    texto
)

texto = "".join(
    caractere
    for caractere in texto
    if not unicodedata.combining(
        caractere
    )
)

# Maiúsculas
texto = texto.upper()

# Substitui caracteres especiais por espaço
texto = re.sub(
    r"[^A-Z0-9]+",
    " ",
    texto
)

# Remove espaços duplicados
texto = re.sub(
    r"\s+",
    " ",
    texto
)

return texto.strip()
```

# ============================================================

# IDENTIFICA COMPROVANTE

# ============================================================

def identificar_comprovante(texto):

```
texto = normalizar_texto(
    texto
)

if not texto:
    return None

# ========================================================
# COMPROVANTE PIX
# ========================================================

# Forma exata:
# COMPROVANTE PIX

if re.search(
    r"\bCOMPROVANTE\s+PIX\b",
    texto
):
    return "PIX"

# COMPROVANTE DE PIX

if re.search(
    r"\bCOMPROVANTE\s+DE\s+PIX\b",
    texto
):
    return "PIX"

# COMPROVANTE DE PAGAMENTO PIX

if re.search(
    r"\bCOMPROVANTE\s+DE\s+PAGAMENTO\s+PIX\b",
    texto
):
    return "PIX"

# PAGAMENTO PIX

if re.search(
    r"\bPAGAMENTO\s+PIX\b",
    texto
):
    return "PIX"

# PIX + COMPROVANTE em qualquer posição
#
# Isso ajuda nos casos em que o banco apresenta:
#
# PIX
# ...
# COMPROVANTE

if (
    re.search(
        r"\bPIX\b",
        texto
    )
    and
    re.search(
        r"\bCOMPROVANTE\b",
        texto
    )
):
    return "PIX"

# ========================================================
# COMPROVANTE DE TRANSFERENCIA
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
# COMPROVANTE DE TRANSACAO BANCARIA
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
# OUTRO COMPROVANTE
# ========================================================

if re.search(
    r"\bCOMPROVANTE\b",
    texto
):
    return "OUTRO_COMPROVANTE"

return None
```

# ============================================================

# FORMATA TAMANHO

# ============================================================

def formatar_tamanho(tamanho):

```
if tamanho < 1024:

    return (
        f"{tamanho} B"
    )

if tamanho < 1024 * 1024:

    return (
        f"{tamanho / 1024:.2f} KB"
    )

return (
    f"{tamanho / (1024 * 1024):.2f} MB"
)
```

# ============================================================

# CRIA PDF A PARTIR DE PÁGINAS

# ============================================================

def criar_pdf(
reader,
paginas
):

```
writer = PdfWriter()

for numero_pagina in paginas:

    writer.add_page(
        reader.pages[
            numero_pagina
        ]
    )

buffer = BytesIO()

writer.write(
    buffer
)

resultado = buffer.getvalue()

del writer

buffer.close()

gc.collect()

return resultado
```

# ============================================================

# AGRUPA PÁGINAS EM PDFs

#

# IMPORTANTE:

#

# Aqui NÃO criamos um PDF para cada comprovante.

#

# As páginas são acumuladas até o PDF chegar perto de 9,5 MB.

# ============================================================

def agrupar_paginas_em_pdfs(
reader,
paginas,
progress_bar,
progresso_inicio,
progresso_fim
):

```
arquivos_pdf = []

grupo_atual = []

total_paginas = len(
    paginas
)

if total_paginas == 0:

    return arquivos_pdf

for indice, numero_pagina in enumerate(
    paginas
):

    # ====================================================
    # PRIMEIRA PÁGINA
    # ====================================================

    if not grupo_atual:

        grupo_atual = [
            numero_pagina
        ]

        continue

    # ====================================================
    # TESTA NOVA PÁGINA
    # ====================================================

    grupo_teste = (
        grupo_atual
        +
        [numero_pagina]
    )

    pdf_teste = criar_pdf(
        reader,
        grupo_teste
    )

    tamanho_teste = len(
        pdf_teste
    )

    # ====================================================
    # AINDA CABE
    # ====================================================

    if tamanho_teste <= LIMITE_BYTES:

        grupo_atual = (
            grupo_teste
        )

    # ====================================================
    # PASSOU DO LIMITE
    # ====================================================

    else:

        # ------------------------------------------------
        # Salva grupo anterior
        # ------------------------------------------------

        pdf_final = criar_pdf(
            reader,
            grupo_atual
        )

        arquivos_pdf.append(
            pdf_final
        )

        # ------------------------------------------------
        # Começa novo grupo
        # ------------------------------------------------

        grupo_atual = [
            numero_pagina
        ]

    # Libera teste
    del pdf_teste

    gc.collect()

    # ====================================================
    # PROGRESSO
    # ====================================================

    progresso = (
        progresso_inicio
        +
        (
            (
                indice + 1
            )
            /
            max(
                total_paginas,
                1
            )
        )
        *
        (
            progresso_fim
            -
            progresso_inicio
        )
    )

    progress_bar.progress(
        int(
            min(
                progresso,
                100
            )
        )
    )

# ========================================================
# ÚLTIMO GRUPO
# ========================================================

if grupo_atual:

    pdf_final = criar_pdf(
        reader,
        grupo_atual
    )

    arquivos_pdf.append(
        pdf_final
    )

return arquivos_pdf
```

# ============================================================

# CRIA ZIPS DE ATÉ 9,5 MB

#

# Os PDFs criados acima são agrupados em ZIPs.

# ============================================================

def criar_zips(
arquivos_pdf,
prefixo
):

```
zips = []

if not arquivos_pdf:

    return zips

zip_buffer = BytesIO()

zip_file = zipfile.ZipFile(
    zip_buffer,
    "w",
    compression=zipfile.ZIP_DEFLATED
)

tamanho_atual = 0

numero_zip = 1

numero_pdf = 1

for pdf_bytes in arquivos_pdf:

    tamanho_pdf = len(
        pdf_bytes
    )

    nome_pdf = (
        f"{prefixo}_"
        f"{numero_pdf:04d}.pdf"
    )

    # ====================================================
    # Se o PDF sozinho já ultrapassar 9,5 MB
    # ====================================================

    if tamanho_pdf > LIMITE_BYTES:

        # Fecha ZIP atual se possuir conteúdo
        if tamanho_atual > 0:

            zip_file.close()

            zips.append({
                "nome":
                    f"{prefixo}_"
                    f"parte_{numero_zip:03d}.zip",

                "dados":
                    zip_buffer.getvalue()
            })

            numero_zip += 1

        # ------------------------------------------------
        # Cria novo ZIP
        # ------------------------------------------------

        zip_buffer = BytesIO()

        zip_file = zipfile.ZipFile(
            zip_buffer,
            "w",
            compression=zipfile.ZIP_DEFLATED
        )

        # ------------------------------------------------
        # Coloca PDF grande sozinho
        # ------------------------------------------------

        zip_file.writestr(
            nome_pdf,
            pdf_bytes
        )

        zip_file.close()

        zips.append({
            "nome":
                f"{prefixo}_"
                f"parte_{numero_zip:03d}.zip",

            "dados":
                zip_buffer.getvalue(),

            "observacao":
                "Este PDF individual ultrapassou 9,5 MB."
        })

        numero_zip += 1

        # ------------------------------------------------
        # Novo ZIP
        # ------------------------------------------------

        zip_buffer = BytesIO()

        zip_file = zipfile.ZipFile(
            zip_buffer,
            "w",
            compression=zipfile.ZIP_DEFLATED
        )

        tamanho_atual = 0

        numero_pdf += 1

        continue

    # ====================================================
    # VERIFICA SE CABE NO ZIP ATUAL
    # ====================================================

    if (
        tamanho_atual > 0
        and
        tamanho_atual
        +
        tamanho_pdf
        >
        LIMITE_BYTES
    ):

        # ------------------------------------------------
        # Fecha ZIP atual
        # ------------------------------------------------

        zip_file.close()

        zips.append({
            "nome":
                f"{prefixo}_"
                f"parte_{numero_zip:03d}.zip",

            "dados":
                zip_buffer.getvalue()
        })

        numero_zip += 1

        # ------------------------------------------------
        # Cria novo ZIP
        # ------------------------------------------------

        zip_buffer = BytesIO()

        zip_file = zipfile.ZipFile(
            zip_buffer,
            "w",
            compression=zipfile.ZIP_DEFLATED
        )

        tamanho_atual = 0

    # ====================================================
    # ADICIONA PDF AO ZIP
    # ====================================================

    zip_file.writestr(
        nome_pdf,
        pdf_bytes
    )

    tamanho_atual += tamanho_pdf

    numero_pdf += 1

# ========================================================
# FECHA ÚLTIMO ZIP
# ========================================================

if tamanho_atual > 0:

    zip_file.close()

    zips.append({
        "nome":
            f"{prefixo}_"
            f"parte_{numero_zip:03d}.zip",

        "dados":
            zip_buffer.getvalue()
    })

else:

    try:

        zip_file.close()

    except Exception:

        pass

return zips
```

# ============================================================

# PROCESSAMENTO PRINCIPAL

# ============================================================

def processar_pdf(
caminho_pdf,
progress_bar,
status
):

```
# ========================================================
# ABRE PDF
# ========================================================

status.info(
    "📖 Abrindo PDF..."
)

reader = PdfReader(
    caminho_pdf
)

total_paginas = len(
    reader.pages
)

# ========================================================
# LISTAS
# ========================================================

paginas_comprovantes = []

paginas_sem_comprovantes = []

contadores = {}

diagnostico = []

# ========================================================
# ANALISA TODAS AS PÁGINAS
# ========================================================

for numero_pagina in range(
    total_paginas
):

    pagina = reader.pages[
        numero_pagina
    ]

    status.info(
        f"🔍 Analisando página "
        f"{numero_pagina + 1} "
        f"de "
        f"{total_paginas}..."
    )

    # ----------------------------------------------------
    # EXTRAÇÃO DO TEXTO
    # ----------------------------------------------------

    try:

        texto = (
            pagina.extract_text()
            or ""
        )

    except Exception as erro:

        texto = ""

    texto_normalizado = (
        normalizar_texto(
            texto
        )
    )

    # ----------------------------------------------------
    # IDENTIFICA
    # ----------------------------------------------------

    tipo = identificar_comprovante(
        texto
    )

    # ====================================================
    # COMPROVANTE
    # ====================================================

    if tipo:

        paginas_comprovantes.append(
            numero_pagina
        )

        contadores[tipo] = (
            contadores.get(
                tipo,
                0
            )
            +
            1
        )

    # ====================================================
    # SEM COMPROVANTE
    # ====================================================

    else:

        paginas_sem_comprovantes.append(
            numero_pagina
        )

    # ====================================================
    # DIAGNÓSTICO
    # ====================================================

    diagnostico.append({

        "pagina":
            numero_pagina + 1,

        "tipo":
            tipo
            if tipo
            else "NAO_COMPROVANTE",

        "tem_pix":
            bool(
                re.search(
                    r"\bPIX\b",
                    texto_normalizado
                )
            ),

        "tem_comprovante":
            bool(
                re.search(
                    r"\bCOMPROVANTE\b",
                    texto_normalizado
                )
            ),

        "texto":
            texto_normalizado[
                :1000
            ]
    })

    # ----------------------------------------------------
    # PROGRESSO
    # ----------------------------------------------------

    progresso = int(
        (
            (
                numero_pagina + 1
            )
            /
            max(
                total_paginas,
                1
            )
        )
        *
        50
    )

    progress_bar.progress(
        progresso
    )

# ========================================================
# AGRUPA COMPROVANTES
# ========================================================

status.info(
    "📄 Agrupando comprovantes..."
)

pdfs_comprovantes = (
    agrupar_paginas_em_pdfs(
        reader,
        paginas_comprovantes,
        progress_bar,
        50,
        70
    )
)

# ========================================================
# AGRUPA SEM COMPROVANTES
# ========================================================

status.info(
    "📄 Agrupando páginas sem comprovantes..."
)

pdfs_sem_comprovantes = (
    agrupar_paginas_em_pdfs(
        reader,
        paginas_sem_comprovantes,
        progress_bar,
        70,
        85
    )
)

# ========================================================
# ZIP COMPROVANTES
# ========================================================

status.info(
    "📦 Criando ZIPs dos comprovantes..."
)

zips_comprovantes = criar_zips(
    pdfs_comprovantes,
    "COMPROVANTES"
)

progress_bar.progress(
    92
)

# ========================================================
# ZIP SEM COMPROVANTES
# ========================================================

status.info(
    "📦 Criando ZIPs sem comprovantes..."
)

zips_sem_comprovantes = criar_zips(
    pdfs_sem_comprovantes,
    "SEM_COMPROVANTES"
)

progress_bar.progress(
    100
)

status.success(
    "✅ Processamento concluído!"
)

# ========================================================
# RESULTADO
# ========================================================

resultado = {

    "total_paginas":
        total_paginas,

    "total_comprovantes":
        len(
            paginas_comprovantes
        ),

    "total_sem_comprovantes":
        len(
            paginas_sem_comprovantes
        ),

    "contadores":
        contadores,

    "diagnostico":
        diagnostico,

    "zips_comprovantes":
        zips_comprovantes,

    "zips_sem_comprovantes":
        zips_sem_comprovantes
}

# Libera memória
del pdfs_comprovantes
del pdfs_sem_comprovantes
del reader

gc.collect()

return resultado
```

# ============================================================

# UPLOAD

# ============================================================

arquivo = st.file_uploader(
"📎 Selecione o arquivo PDF",
type=["pdf"],
help="Selecione o PDF mensal."
)

# ============================================================

# ARQUIVO SELECIONADO

# ============================================================

if arquivo is not None:

```
tamanho_original = len(
    arquivo.getbuffer()
)

st.success(
    f"✅ Arquivo selecionado: "
    f"**{arquivo.name}**"
)

st.write(
    f"📦 Tamanho do arquivo: "
    f"**{formatar_tamanho(tamanho_original)}**"
)

st.caption(
    f"Os arquivos de saída serão agrupados "
    f"em aproximadamente {LIMITE_MB} MB."
)

# ========================================================
# BOTÃO PROCESSAR
# ========================================================

if st.button(
    "🚀 PROCESSAR PDF",
    type="primary",
    use_container_width=True
):

    progress_bar = st.progress(
        0
    )

    status = st.empty()

    pasta_trabalho = tempfile.mkdtemp(
        prefix="separador_"
    )

    caminho_pdf = os.path.join(
        pasta_trabalho,
        "arquivo_original.pdf"
    )

    try:

        # ------------------------------------------------
        # SALVA PDF
        # ------------------------------------------------

        status.info(
            "💾 Salvando arquivo..."
        )

        with open(
            caminho_pdf,
            "wb"
        ) as arquivo_saida:

            arquivo_saida.write(
                arquivo.getbuffer()
            )

        # ------------------------------------------------
        # PROCESSA
        # ------------------------------------------------

        resultado = processar_pdf(
            caminho_pdf,
            progress_bar,
            status
        )

        # ------------------------------------------------
        # GUARDA NO SESSION STATE
        # ------------------------------------------------

        st.session_state[
            "resultado"
        ] = resultado

    except Exception as erro:

        status.error(
            "❌ Erro durante o processamento."
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

        gc.collect()
```

# ============================================================

# MOSTRA RESULTADO

# ============================================================

if "resultado" in st.session_state:

```
resultado = (
    st.session_state[
        "resultado"
    ]
)

st.divider()

st.header(
    "📊 Resultado"
)

# ========================================================
# INDICADORES
# ========================================================

col1, col2, col3 = st.columns(3)

with col1:

    st.metric(
        "📄 Total de páginas",
        resultado[
            "total_paginas"
        ]
    )

with col2:

    st.metric(
        "🧾 Comprovantes encontrados",
        resultado[
            "total_comprovantes"
        ]
    )

with col3:

    st.metric(
        "📑 Sem comprovantes",
        resultado[
            "total_sem_comprovantes"
        ]
    )

# ========================================================
# TIPOS
# ========================================================

contadores = resultado[
    "contadores"
]

if contadores:

    st.subheader(
        "🔎 Comprovantes encontrados por tipo"
    )

    quantidade_colunas = min(
        4,
        len(contadores)
    )

    colunas = st.columns(
        quantidade_colunas
    )

    for indice, (
        tipo,
        quantidade
    ) in enumerate(
        sorted(
            contadores.items()
        )
    ):

        with colunas[
            indice % quantidade_colunas
        ]:

            st.metric(
                tipo.replace(
                    "_",
                    " "
                ),
                quantidade
            )

# ========================================================
# COMPROVANTES
# ========================================================

st.divider()

st.subheader(
    "📦 COMPROVANTES"
)

zips_comprovantes = (
    resultado[
        "zips_comprovantes"
    ]
)

if zips_comprovantes:

    st.success(
        f"✅ "
        f"{len(zips_comprovantes)} "
        f"ZIP(s) de comprovantes."
    )

    for indice, item in enumerate(
        zips_comprovantes
    ):

        tamanho_zip = len(
            item[
                "dados"
            ]
        )

        st.write(
            f"📦 **{item['nome']}**"
        )

        st.caption(
            f"Tamanho: "
            f"{formatar_tamanho(tamanho_zip)}"
        )

        if (
            "observacao"
            in item
        ):

            st.warning(
                item[
                    "observacao"
                ]
            )

        st.download_button(
            label=(
                f"⬇️ Baixar "
                f"{item['nome']}"
            ),

            data=item[
                "dados"
            ],

            file_name=item[
                "nome"
            ],

            mime="application/zip",

            key=(
                "download_comp_"
                +
                str(indice)
            ),

            use_container_width=True
        )

else:

    st.warning(
        "⚠️ Nenhum comprovante foi encontrado."
    )

# ========================================================
# SEM COMPROVANTES
# ========================================================

st.divider()

st.subheader(
    "📦 SEM COMPROVANTES"
)

zips_sem = resultado[
    "zips_sem_comprovantes"
]

if zips_sem:

    st.info(
        f"📄 "
        f"{len(zips_sem)} "
        f"ZIP(s) sem comprovantes."
    )

    for indice, item in enumerate(
        zips_sem
    ):

        tamanho_zip = len(
            item[
                "dados"
            ]
        )

        st.write(
            f"📦 **{item['nome']}**"
        )

        st.caption(
            f"Tamanho: "
            f"{formatar_tamanho(tamanho_zip)}"
        )

        if (
            "observacao"
            in item
        ):

            st.warning(
                item[
                    "observacao"
                ]
            )

        st.download_button(
            label=(
                f"⬇️ Baixar "
                f"{item['nome']}"
            ),

            data=item[
                "dados"
            ],

            file_name=item[
                "nome"
            ],

            mime="application/zip",

            key=(
                "download_sem_"
                +
                str(indice)
            ),

            use_container_width=True
        )

else:

    st.success(
        "✅ Não existem páginas sem comprovantes."
    )

# ========================================================
# DIAGNÓSTICO
# ========================================================

st.divider()

with st.expander(
    "🔍 Diagnóstico — texto encontrado em cada página"
):

    diagnostico = resultado[
        "diagnostico"
    ]

    st.write(
        f"Total analisado: "
        f"**{len(diagnostico)} páginas**"
    )

    for item in diagnostico:

        pagina = item[
            "pagina"
        ]

        tipo = item[
            "tipo"
        ]

        tem_pix = item[
            "tem_pix"
        ]

        tem_comprovante = item[
            "tem_comprovante"
        ]

        texto = item[
            "texto"
        ]

        # ------------------------------------------------
        # COMPROVANTE
        # ------------------------------------------------

        if tipo != "NAO_COMPROVANTE":

            st.success(
                f"Página {pagina} "
                f"→ **{tipo}**"
            )

            st.code(
                texto
            )

        # ------------------------------------------------
        # PIX NÃO CLASSIFICADO
        # ------------------------------------------------

        elif tem_pix:

            st.warning(
                f"Página {pagina} "
                f"→ contém PIX, "
                f"mas não foi classificada."
            )

            st.code(
                texto
            )

        # ------------------------------------------------
        # COMPROVANTE NÃO CLASSIFICADO
        # ------------------------------------------------

        elif tem_comprovante:

            st.info(
                f"Página {pagina} "
                f"→ contém COMPROVANTE."
            )

            st.code(
                texto
            )
```
