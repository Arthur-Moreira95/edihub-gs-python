# 🧠 Edihub · Scraper de Editais & Cérebro Conectado

**Global Solution 2026.2 · CitizenTech · Computational Thinking with Python**
FIAP · Engenharia de Software · 1º ano · Rio de Janeiro

O ESP32 do **Edihub Totem Escolar** publica no ThingSpeak quantos alunos se aproximaram do totem e a luz ambiente. Este programa é o "cérebro" do sistema. Ele busca essas leituras pela API, cruza as duas medidas num **Índice de Risco de baixo engajamento** e avisa quando a situação piora, ou seja, quando os alunos deixam de ver os prazos dos vestibulares. Ele também mantém a função original do Edihub: **raspar os sites das instituições e baixar os editais novos**.

- Canal ThingSpeak (público): https://thingspeak.mathworks.com/channels/3584126

---
## Integrantes

| Nome | RM |
| --- | --- |
| Bernardo de Paula Rodrigues | 572376 |
| Arthur Moreira Costa | 571532 |
| Henrique Nunes Mororó | 574073 |

---

## ▶️ Como rodar

Requisito: Python 3.9 ou mais recente. No Windows, se o comando `py` não funcionar, use `python`.

```bash
py -m pip install requests beautifulsoup4
cd python
py main.py
```

| Opção | O que faz |
| :---: | :--- |
| 1 a 3 | Raspa o site da ESPM, da PUC-Rio ou da FIAP e baixa os editais novos para `editais_baixados/` |
| 4 | Busca as leituras do totem no ThingSpeak, atualiza o histórico e o CSV e mostra o relatório de alerta |
| 5 | Sair |

---

## 📁 Arquivos

| Arquivo | Função |
| :--- | :--- |
| `main.py` | Programa completo, em funções com tipo e docstring |
| `backup.json` | Última resposta da API que deu certo. É o **plano B** quando não há rede |
| `historico.json` | Todas as leituras do totem, acumuladas sem repetir |
| `relatorio.csv` | Histórico exportado com cabeçalho (separador `;`) |
| `historico_editais.json` | Editais já baixados, para não baixar de novo (criado na 1ª raspagem) |
| `prompts.md` | Prompts usados com IA |

---

## 📐 Índice de Risco

```
nivel = (valor - min) / (max - min) * 100      → limitado entre 0 e 100
risco = peso1 * nivel1 + peso2 * nivel2         → os pesos somam 1
```

| Medida | Mín. | Máx. | Peso | Justificativa |
| :--- | :---: | :---: | :---: | :--- |
| Aproximações (`field1`) | 0 | 3 | **0,7** | É a medida direta de engajamento: o totem existe para ser consultado. Nos testes, o ESP32 registrou de 0 a 2 aproximações por envio. |
| Luz ambiente (`field3`, em %) | 0 | 100 | **0,3** | Com o corredor escuro, o display fica difícil de ler e há pouco movimento. Pesa menos porque é uma causa indireta. |

Nas duas medidas, **quanto menor o valor, maior o risco**. Por isso o programa calcula o nível com a fórmula e depois usa `100 - nivel`, controlado pela opção `"invertido": True` no `CONFIG`.

**Faixas:** NORMAL abaixo de 40 · ATENÇÃO de 40 a 70 · PERIGO a partir de 70.

**Exemplo:** 0 aproximações com luz em 76% → níveis 100 e 24 → risco = 0,7 × 100 + 0,3 × 24 = **77,2 → PERIGO**.

---

## ✅ Requisitos e onde estão no código

| # | Requisito | Função |
| :---: | :--- | :--- |
| 1 | Dados reais: 40 leituras com 2 campos, `timeout`, status conferido e `RequestException` tratada | `buscar_feeds_thingspeak()` |
| 2 | Plano B: sem rede, lê o `backup.json`; cada busca que dá certo atualiza o backup | `obter_feeds()` |
| 3 | Modelo: cada leitura é um dicionário `{id, horario, medidas, faixa}`; limites, pesos e avisos ficam no `CONFIG` | `criar_leitura()`, `montar_leituras()` |
| 4 | Decisão combinada e `raise ValueError` para configuração inválida | `calcular_nivel()`, `calcular_risco()`, `classificar_faixa()`, `validar_config()` |
| 5 | Análise: tendência (3 altas seguidas = PIORANDO), maior episódio em PERIGO e contagem por faixa | `detectar_tendencia()`, `analisar_episodios_perigo()`, `contar_faixas()` |
| 6 | Memória: histórico sem repetir (`entry_id` num `set`) e CSV com cabeçalho | `atualizar_historico()`, `exportar_csv()` |

**Nada derruba o programa:**
- Falta de rede ou status de erro → plano B.
- Arquivo ausente ou corrompido → lista vazia.
- Leitura com campo vazio → é ignorada.
- Erro ao gravar arquivo → aviso.
- Opção inválida → o menu pergunta de novo.
- Ctrl+C → encerra sem erro.
- BeautifulSoup não instalado → só a raspagem avisa; o resto funciona.

---

## 🔗 Integração

- **Edge Computing:** o programa lê os campos que o ESP32 do totem publica.
- **Software & TX Design:** o menu, os avisos e o alerta de PIORANDO seguem a jornada do aluno.
- **Front-end e Web Development:** as faixas e os avisos são os mesmos da página, e o `historico.json` e o `relatorio.csv` podem alimentar o JavaScript.
- **Storytelling:** a opção 4 buscando os dados ao vivo entra no vídeo como prova.

---

## 🖥️ Execução

Opção 4 executada sem internet, usando o plano B com as 34 leituras reais do canal:

```
--- ANALISANDO DADOS DO TOTEM (THINGSPEAK) ---
[Plano B] Usando as leituras salvas no backup.json.
[CSV] 34 leituras exportadas para relatorio.csv

=== Alerta Engajamento · Edihub Totem Escolar ===
backup.json: 34 novas · histórico 34
Risco médio 45 · pico 77 às 17:42
PERIGO: 4 episódio(s) · o maior durou 1 min (4 leituras)
Tendência: ESTÁVEL
Faixas: NORMAL 15 · ATENÇÃO 11 · PERIGO 8
Agora: risco 77 (PERIGO) - Totem ignorado ou no escuro: confira a iluminação e avise as turmas.
```

<!-- Coloquem aqui o print da opção 4 rodando com internet (linha começando com "ThingSpeak:"):
![Execução](print-execucao.png) -->
