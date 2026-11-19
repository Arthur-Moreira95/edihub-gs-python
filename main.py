import csv
import hashlib
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import requests

# o BeautifulSoup só é usado na raspagem. Sem ele, a parte do ThingSpeak continua funcionando.
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

PASTA_BASE_DESTINO = "./editais_baixados"
ARQUIVO_HISTORICO_EDITAIS = "historico_editais.json"
ARQUIVO_BACKUP = "backup.json"
ARQUIVO_HISTORICO = "historico.json"
ARQUIVO_CSV = "relatorio.csv"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

THINGSPEAK_CHANNEL_ID = "3584126"
THINGSPEAK_URL = (
    f"https://api.thingspeak.com/channels/{THINGSPEAK_CHANNEL_ID}/feeds.json"
    "?results=40&timezone=America/Sao_Paulo"
)

# limites, pesos e avisos do Índice de Risco (justificativa no README).
# "invertido": nas duas medidas, quanto MENOR o valor, MAIOR o risco.
CONFIG = {
    "medidas": {
        "aproximacoes": {"campo": "field1", "min": 0, "max": 3, "peso": 0.7, "invertido": True},
        "luz": {"campo": "field3", "min": 0, "max": 100, "peso": 0.3, "invertido": True},
    },
    "faixas": {"atencao": 40, "perigo": 70},
    "avisos": {
        "NORMAL": "Totem visível e com alunos consultando os prazos.",
        "ATENÇÃO": "Pouca interação com o totem: reforce a divulgação dos prazos.",
        "PERIGO": "Totem ignorado ou no escuro: confira a iluminação e avise as turmas.",
        "PIORANDO": "Engajamento caindo: divulgue os prazos no mural e nos grupos da escola.",
    },
}

PALAVRAS_CHAVE = (
    "edital", "retificacao", "retificação", "manual", "anexo",
    "convocacao", "convocação", "resultado", "processo-seletivo",
    "processo seletivo", "vestibular", "regulamento", "norma"
)
EXTENSOES_DOCUMENTO = (".pdf", ".doc", ".docx", ".odt", ".rtf", ".xls", ".xlsx")

OPCOES_URLS = {
    "1": ("ESPM - Vestibular", "https://www.espm.br/cursos-de-graduacao/processos-seletivos/vestibular/", "ESPM_Vestibular"),
    "2": ("PUC-Rio - Medicina", "https://www.puc-rio.br/ensinopesq/ccg/medicina/vestibular-medicina.html", "PUC_Rio_Medicina"),
    "3": ("FIAP - Vestibular", "https://www.fiap.com.br/graduacao/vestibular/", "FIAP_Vestibular")
}



# arq JSON

def carregar_json(caminho: str, padrao):
    """Lê um arquivo JSON. Se ele não existir ou estiver corrompido, devolve o padrão."""
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return padrao


def salvar_json(caminho: str, dados) -> None:
    """Grava os dados num arquivo JSON sem derrubar o programa se der erro."""
    try:
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(dados, f, indent=4, ensure_ascii=False)
    except OSError as e:
        print(f"[Erro] Não foi possível salvar {caminho}: {e}")



# thingSpeak: dados reais + plano B

def validar_config() -> None:
    """Dispara ValueError se os pesos não somarem 1 ou se algum mínimo for >= máximo."""
    soma = sum(regra["peso"] for regra in CONFIG["medidas"].values())
    if round(soma, 6) != 1:
        raise ValueError(f"Os pesos precisam somar 1 (estão somando {soma}).")
    for nome, regra in CONFIG["medidas"].items():
        if regra["min"] >= regra["max"]:
            raise ValueError(f"Em '{nome}', o mínimo precisa ser menor que o máximo.")


def buscar_feeds_thingspeak() -> Optional[List[dict]]:
    """Busca as últimas 40 leituras do canal. Devolve a lista de feeds ou None se falhar."""
    try:
        resp = requests.get(THINGSPEAK_URL, timeout=10)
        if resp.status_code != 200:
            print(f"[ThingSpeak] Servidor retornou status {resp.status_code}.")
            return None
        dados = resp.json()
        if isinstance(dados, dict):
            return dados.get("feeds", [])
        print("[ThingSpeak] Resposta inesperada. Verifique o Channel ID.")
    except requests.exceptions.RequestException as e:
        print(f"[ThingSpeak] Erro de rede ao conectar à API: {e}")
    except ValueError:
        print("[ThingSpeak] A resposta não é um JSON válido.")
    return None


def obter_feeds() -> Tuple[List[dict], str]:
    """usa a API e atualiza o backup. Se a API falhar, lê o backup.json (plano B)."""
    feeds = buscar_feeds_thingspeak()
    if feeds:
        salvar_json(ARQUIVO_BACKUP, feeds)
        return feeds, "ThingSpeak"
    print("[Plano B] Usando as leituras salvas no backup.json.")
    return carregar_json(ARQUIVO_BACKUP, []), "backup.json"



# indice de Risco

def calcular_nivel(valor: float, regra: dict) -> float:
    """Aplica a fórmula nivel = (valor - min) / (max - min) * 100, limitada entre 0 e 100."""
    nivel = (valor - regra["min"]) / (regra["max"] - regra["min"]) * 100
    nivel = max(0, min(100, nivel))
    if regra["invertido"]:
        nivel = 100 - nivel
    return nivel


def calcular_risco(medidas: Dict[str, float]) -> float:
    """calcula risco = peso1 * nivel1 + peso2 * nivel2."""
    risco = 0
    for nome, regra in CONFIG["medidas"].items():
        risco += regra["peso"] * calcular_nivel(medidas[nome], regra)
    return round(risco, 1)


def classificar_faixa(risco: float) -> str:
    """Devolve a faixa do risco: NORMAL, ATENÇÃO ou PERIGO."""
    if risco >= CONFIG["faixas"]["perigo"]:
        return "PERIGO"
    if risco >= CONFIG["faixas"]["atencao"]:
        return "ATENÇÃO"
    return "NORMAL"


def criar_leitura(feed: dict) -> Optional[dict]:
    """transforma um feed da API no dicionário {id, horario, medidas, risco, faixa}."""
    try:
        medidas = {}
        for nome, regra in CONFIG["medidas"].items():
            medidas[nome] = float(feed[regra["campo"]])
        risco = calcular_risco(medidas)
        return {
            "id": int(feed["entry_id"]),
            "horario": feed["created_at"][:19].replace("T", " "),
            "medidas": medidas,
            "risco": risco,
            "faixa": classificar_faixa(risco),
        }
    except (KeyError, TypeError, ValueError):
        return None  # leitura com campo vazio ou inválido é ignorada


def montar_leituras(feeds: List[dict]) -> List[dict]:
    """Converte todos os feeds em leituras, ignorando as inválidas."""
    leituras = []
    for feed in feeds:
        leitura = criar_leitura(feed)
        if leitura is not None:
            leituras.append(leitura)
    return leituras



# memória: histórico sem repetir e CSV

def atualizar_historico(novas: List[dict]) -> Tuple[List[dict], int]:
    """Junta as leituras novas ao historico.json sem repetir (entry_id num set)."""
    historico = carregar_json(ARQUIVO_HISTORICO, [])
    if not isinstance(historico, list):
        historico = []
    ids_salvos: Set[int] = {leitura["id"] for leitura in historico}

    adicionadas = 0
    for leitura in novas:
        if leitura["id"] not in ids_salvos:
            historico.append(leitura)
            ids_salvos.add(leitura["id"])
            adicionadas += 1

    historico.sort(key=lambda leitura: leitura["id"])
    salvar_json(ARQUIVO_HISTORICO, historico)
    return historico, adicionadas


def exportar_csv(historico: List[dict]) -> None:
    """Exporta o histórico para relatorio.csv com cabeçalho."""
    try:
        with open(ARQUIVO_CSV, "w", newline="", encoding="utf-8-sig") as f:
            escritor = csv.writer(f, delimiter=";")
            escritor.writerow(["id", "horario", "aproximacoes", "luz", "risco", "faixa"])
            for l in historico:
                escritor.writerow([l["id"], l["horario"], l["medidas"]["aproximacoes"],
                                   l["medidas"]["luz"], l["risco"], l["faixa"]])
        print(f"[CSV] {len(historico)} leituras exportadas para {ARQUIVO_CSV}")
    except OSError as e:
        print(f"[Erro] Não foi possível exportar o CSV: {e}")



# análise

def detectar_tendencia(leituras: List[dict]) -> str:
    """PIORANDO se o risco subiu 3 vezes seguidas nas últimas leituras."""
    riscos = [leitura["risco"] for leitura in leituras[-4:]]
    if len(riscos) == 4 and riscos[0] < riscos[1] < riscos[2] < riscos[3]:
        return "PIORANDO"
    if len(riscos) == 4 and riscos[0] > riscos[1] > riscos[2] > riscos[3]:
        return "MELHORANDO"
    return "ESTÁVEL"


def analisar_episodios_perigo(leituras: List[dict]) -> Tuple[int, List[dict]]:
    """Conta os episódios seguidos em PERIGO e devolve (quantidade, leituras do maior episódio)."""
    quantidade = 0
    atual: List[dict] = []
    maior: List[dict] = []
    for leitura in leituras:
        if leitura["faixa"] == "PERIGO":
            if not atual:
                quantidade += 1
            atual.append(leitura)
            if len(atual) > len(maior):
                maior = list(atual)
        else:
            atual = []
    return quantidade, maior


def calcular_minutos(inicio: str, fim: str) -> int:
    """Calcula quantos minutos se passaram entre dois horários."""
    formato = "%Y-%m-%d %H:%M:%S"
    diferenca = datetime.strptime(fim, formato) - datetime.strptime(inicio, formato)
    return int(diferenca.total_seconds() // 60)


def contar_faixas(leituras: List[dict]) -> Dict[str, int]:
    """Conta quantas leituras caíram em cada faixa."""
    contagem = {"NORMAL": 0, "ATENÇÃO": 0, "PERIGO": 0}
    for leitura in leituras:
        contagem[leitura["faixa"]] += 1
    return contagem


def exibir_relatorio(leituras: List[dict], origem: str, novas: int, total: int) -> None:
    """Mostra o relatório: risco médio, pico, episódios em PERIGO, tendência e faixas."""
    print("\n=== Alerta Engajamento · Edihub Totem Escolar ===")
    print(f"{origem}: {novas} novas · histórico {total}")
    if not leituras:
        print("Nenhuma leitura disponível para analisar.")
        return

    media = sum(l["risco"] for l in leituras) / len(leituras)
    pico = max(leituras, key=lambda l: l["risco"])
    print(f"Risco médio {media:.0f} · pico {pico['risco']:.0f} às {pico['horario'][11:16]}")

    quantidade, maior = analisar_episodios_perigo(leituras)
    if quantidade:
        minutos = calcular_minutos(maior[0]["horario"], maior[-1]["horario"])
        print(f"PERIGO: {quantidade} episódio(s) · o maior durou {minutos} min ({len(maior)} leituras)")
    else:
        print("PERIGO: nenhum episódio")

    tendencia = detectar_tendencia(leituras)
    print(f"Tendência: {tendencia}")

    contagem = contar_faixas(leituras)
    print(f"Faixas: NORMAL {contagem['NORMAL']} · ATENÇÃO {contagem['ATENÇÃO']} · PERIGO {contagem['PERIGO']}")

    ultima = leituras[-1]
    print(f"Agora: risco {ultima['risco']:.0f} ({ultima['faixa']}) - {CONFIG['avisos'][ultima['faixa']]}")
    if tendencia == "PIORANDO":
        print(f"AVISO: {CONFIG['avisos']['PIORANDO']}")


def analisar_thingspeak() -> None:
    """Busca as leituras, atualiza histórico e CSV e mostra o relatório."""
    print("\n--- ANALISANDO DADOS DO TOTEM (THINGSPEAK) ---")
    feeds, origem = obter_feeds()
    leituras = montar_leituras(feeds)
    historico, novas = atualizar_historico(leituras)
    exportar_csv(historico)
    exibir_relatorio(leituras, origem, novas, len(historico))



# Raspagem de editais

def extrair_links_com_palavras_chave(url_pagina: str) -> List[str]:
    """Varre o HTML cruzando o texto do link e a URL com as palavras-chave mapeadas."""
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(url_pagina, headers=headers, timeout=15)
        if resp.status_code != 200:
            print(f"[Erro] Falha ao acessar página. Status: {resp.status_code}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        links_encontrados = []

        for tag in soup.find_all("a", href=True):
            href = tag["href"].strip()
            if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
                continue

            url_absoluta = urljoin(url_pagina, href)
            texto = " ".join(tag.stripped_strings)
            referencia = f"{texto} {href}".lower()

            parece_documento = urlparse(url_absoluta).path.lower().endswith(EXTENSOES_DOCUMENTO)
            relevante = any(palavra in referencia for palavra in PALAVRAS_CHAVE)

            if (parece_documento or relevante) and url_absoluta not in links_encontrados:
                links_encontrados.append(url_absoluta)

        return links_encontrados
    except requests.exceptions.RequestException as e:
        print(f"[Erro de Rede] {e}")
        return []


def baixar_arquivo(link: str, pasta_destino: str) -> bool:
    """Baixa o link se ele for um documento. Devolve True se o arquivo foi salvo."""
    headers = {"User-Agent": USER_AGENT}
    try:
        with requests.get(link, headers=headers, stream=True, timeout=15, allow_redirects=True) as resp:
            if resp.status_code != 200:
                print(f"[Erro] Status {resp.status_code} para {link}")
                return False

            tipo = resp.headers.get("Content-Type", "").lower()
            caminho_url = urlparse(resp.url).path.lower()
            eh_documento = (
                caminho_url.endswith(EXTENSOES_DOCUMENTO)
                or any(t in tipo for t in ("pdf", "msword", "officedocument", "opendocument"))
            )
            if not eh_documento:
                print(f"[Ignorado] Link não aponta para binário direto: {link}")
                return False

            nome_arquivo = os.path.basename(urlparse(resp.url).path) or "documento.pdf"
            if not os.path.splitext(nome_arquivo)[1]:
                nome_arquivo += ".pdf" if "pdf" in tipo else ".bin"
            caminho = os.path.join(pasta_destino, nome_arquivo)

            with open(caminho, "wb") as f:
                for bloco in resp.iter_content(chunk_size=8192):
                    if bloco:
                        f.write(bloco)
            print(f"[Sucesso] Salvo em: {caminho}")
            return True
    except requests.exceptions.RequestException as e:
        print(f"[Erro de Rede] {e}")
    except OSError as e:
        print(f"[Erro] Não foi possível salvar o arquivo: {e}")
    return False


def executar_scraping(url_alvo: str, nome_subpasta: str) -> None:
    """Raspa a página escolhida e baixa só os editais que ainda não estão no histórico."""
    if BeautifulSoup is None:
        print("[Aviso] Instale o BeautifulSoup para raspar: py -m pip install beautifulsoup4")
        return

    pasta_destino = os.path.join(PASTA_BASE_DESTINO, nome_subpasta)
    os.makedirs(pasta_destino, exist_ok=True)
    historico = set(carregar_json(ARQUIVO_HISTORICO_EDITAIS, []))

    print(f"\nVarrendo links em: {url_alvo}")
    links = extrair_links_com_palavras_chave(url_alvo)
    if not links:
        print("[Aviso] Nenhum link compatível encontrado.")
        return

    baixados_contador = 0
    for link in links:
        h = hashlib.sha256(link.encode()).hexdigest()
        if h in historico:
            print(f"[Ignorado] Já presente no histórico: {link}")
        elif baixar_arquivo(link, pasta_destino):
            historico.add(h)
            baixados_contador += 1

    salvar_json(ARQUIVO_HISTORICO_EDITAIS, list(historico))
    print(f"Processo concluído. {baixados_contador} novo(s) arquivo(s) baixado(s).")


# menu

def exibir_menu() -> None:
    """Mostra o menu em loop até o usuário escolher Sair."""
    while True:
        print("\n--- EDIHUB: SCRAPER DE EDITAIS & CÉREBRO CONECTADO ---")
        print("Selecione uma opção:")
        for k, (nome, _, _) in OPCOES_URLS.items():
            print(f"{k}. Raspar e baixar de {nome}")
        print("4. Analisar dados do Totem (ThingSpeak)")
        print("5. Sair")

        try:
            opcao = input("Escolha uma opção: ").strip()
        except (KeyboardInterrupt, EOFError):
            opcao = "5"

        if opcao in OPCOES_URLS:
            _, url_escolhida, subpasta = OPCOES_URLS[opcao]
            executar_scraping(url_escolhida, subpasta)
        elif opcao == "4":
            analisar_thingspeak()
        elif opcao == "5":
            print("Encerrando execução.")
            break
        else:
            print("Opção inválida. Tente novamente.")


if __name__ == "__main__":
    try:
        validar_config()
    except ValueError as e:
        print(f"[Configuração inválida] {e}")
    else:
        exibir_menu()
