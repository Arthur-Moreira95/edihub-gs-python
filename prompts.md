# Prompts usados com IA

Ferramenta: Claude (Anthropic). A equipe revisou, executou e entendeu todo o código antes de entregar.

## Prompt 1
> Analise meu arquivo python e veja se ele segue os requerimentos do professor

*(enviado junto com o `main.py` antigo e os 3 slides da atividade)*

**Resposta resumida:** o arquivo antigo era um scraper de editais que só gravava uma contagem no ThingSpeak. Ele não lia os campos do ESP32 e não tinha índice de risco, plano B, análise nem CSV.

## Prompt 2
> Então faça as alterações para mim para eu tirar 10/10

**Resposta resumida:** a IA reescreveu o `main.py` para ler os 3 campos do canal 3584126 (aproximações, certame e luz). Ela também criou o Índice de Risco com a fórmula da atividade, o plano B com `backup.json`, a análise (tendência, episódios e faixas), o histórico sem repetição, o CSV e os extras opcionais, e escreveu este README.

## Prompt 3
> Deixe só o principal do thingspeak que o professor pede (pode tirar as comparações de hoje x ontem que tem, acho q o professor não pede isso, certo?) e coloque de volta a raspagem

**Resposta resumida:** a IA removeu os extras opcionais (ranking, busca por horário e comparação hoje x ontem) e trouxe a raspagem de editais do código antigo como opção 5 do menu, dividida em funções menores e sem gravar nada no canal do ThingSpeak.

## Prompt 4
> Refaça simplificando o código e deixando mais parecido possivel desse que anexei pois irei ter que explicar o código depois. Porém mantenha somente a parte do código que seja essencial para eu tirar 10

**Resposta resumida:** a IA reescreveu o programa no estilo do código original do Edihub, com o mesmo menu (1 a 3 raspam, 4 analisa o ThingSpeak, 5 sai) e as mesmas funções de raspagem. A parte do ThingSpeak ficou só com o que é avaliado, e o envio de dados com a Write API Key foi removido.

## Decisões da equipe
- Medidas, limites e pesos: aproximações de 0 a 3 com peso 0,7 e luz de 0 a 100 com peso 0,3, as duas invertidas. A justificativa está no README.
<!-- Acrescentem aqui outros prompts que vocês usarem até a entrega -->
