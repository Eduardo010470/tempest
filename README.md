# Tempest

Uma blockchain escrita do zero em Python, sem nenhuma dependência externa.
Roda num celular Android, dentro do Termux, em 2920 linhas.

O `pip install` nunca foi chamado neste projeto. Só a biblioteca padrão do
Python: `hashlib`, `hmac`, `json`, `secrets`, `http.server`. A curva
elíptica, a assinatura de Schnorr, a árvore de Merkle, a partilha de um
segredo e a derivação da semente de doze palavras estão escritas aqui, à
mão.

## O que isto é, e o que não é

**É** uma blockchain completa e honesta, no sentido de que não há atalho
escondido: as assinaturas são verificadas de verdade, a prova de trabalho é
real, a dificuldade é recalculada pela própria cadeia, e um nó confere tudo
do zero sem confiar em ninguém.

**Não é** uma criptomoeda com valor. Não há rede pública, não há exchange,
não há ninguém para quem vender. O TEMP vale exatamente zero, e isso é
proposital — o objetivo é entender o mecanismo, não vender um token.

Se você veio procurando um projeto para investir, não é aqui. Se você veio
para finalmente entender o que acontece por dentro, bem-vindo.

## Começando

```bash
git clone https://github.com/Eduardo010470/tempest.git
cd tempest
python3 cadeia.py carteira      # cria a carteira e mostra as 12 palavras
python3 cadeia.py minerar       # minera o primeiro bloco
python3 cadeia.py cadeia        # mostra a cadeia
python3 cadeia.py validar       # confere tudo, do bloco zero
```

Precisa de Python 3.8 ou mais novo. Mais nada.

## Os três ataques

É a parte que vale a visita. Em vez de afirmar que a blockchain é segura,
o projeto deixa você atacá-la e ver a recusa acontecer.

### 1. Mexer no passado

```bash
python3 cadeia.py adulterar 3
python3 cadeia.py validar
```

Altera os valores das transações do bloco 3. A validação recusa porque a
raiz de Merkle do bloco deixou de corresponder ao conteúdo dele — e mesmo
que você corrigisse a raiz, o hash do bloco mudaria, e o bloco 4 aponta
para o hash antigo, e assim até o fim da cadeia. É o que "imutável"
significa na prática: não é que não se pode mudar, é que mudar quebra tudo
o que veio depois.

### 2. Repetir uma transação

```bash
python3 cadeia.py enviar <endereço> 10 2
python3 cadeia.py minerar
python3 cadeia.py repetir        # devolve a transação confirmada para a fila
python3 cadeia.py minerar        # e o minerador a descarta
```

Este é o ataque mais instrutivo dos três. A transação devolvida à fila tem
**assinatura autêntica** — não foi tocada. É exatamente o que um atacante
teria: uma ordem de pagamento legítima, assinada pela vítima, pronta para
ser cobrada de novo. E é recusada.

A lição: uma assinatura válida não é uma autorização. Autorização é
assinatura válida **mais** um estado que ainda a aceita. Cada transação
carrega, assinado junto, o seu número de ordem na vida do remetente, e esse
número só serve uma vez. O Bitcoin resolve o mesmo problema de outro jeito,
com UTXOs; o Ethereum resolve com um *nonce* por conta, que é o caminho
seguido aqui.

### 3. Mentir no relógio

```bash
python3 cadeia.py atrasar
```

A dificuldade é calculada em cima dos horários dos blocos, e os horários são
escritos pelo próprio minerador. Então bastaria datar o bloco no passado
para a janela parecer longa, a dificuldade cair, e minerar barato.

Este comando minera um bloco **de verdade** — gasta a prova de trabalho
inteira, acha o nonce, o hash fecha, o encadeamento está correto, as
transações são legítimas, a raiz de Merkle bate. A única coisa falsa é a
hora. E é recusado, porque o horário tem que ser maior que a mediana dos
onze blocos anteriores e não pode estar muito à frente do presente. Nada é
gravado: o ataque é montado na memória e submetido à validação, como um nó
faria ao receber de um estranho.

Uma honestidade sobre essa defesa: ela **limita** o ataque, não o elimina.
Entre o piso da mediana e o teto do futuro ainda sobra uma folga, e quem
tiver a maioria da rede move a mediana. O Bitcoin tem a mesma fragilidade
residual — é o *time-warp*, conhecido e já explorado na testnet dele.
Ninguém resolveu isso de graça; o que se faz é deixar a folga pequena
demais para valer a pena.

## A rede

Com um nó só, quem escreve a cadeia é dono dela. O problema interessante
começa com dois, porque eles podem discordar e não existe árbitro. A regra
que resolve o empate:

> vence a cadeia válida com mais trabalho acumulado

Como a dificuldade varia, "mais trabalho" não é "mais blocos": um bloco de
seis zeros custou dezesseis vezes mais que um de cinco. A conta é a soma do
trabalho de cada bloco, igual ao Bitcoin.

```bash
python3 no.py sou http://SEU_IP:5000      # como eu me apresento
python3 no.py servir 5000                 # põe o nó no ar
python3 no.py conhecer http://OUTRO:5000  # apresenta este nó a um par
python3 no.py rodada                      # conversa com todos os pares
```

Duas coisas que todo nó de verdade faz, e este faz:

**Reorganização.** Quando a cadeia de fora ganha, os blocos descartados
levavam transações dentro — e elas não podem evaporar. Voltam para a fila e
brigam por um lugar nos blocos novos. É daí que vem a regra prática de
esperar confirmações: a sua transação não está firme por estar num bloco,
está firme quando desfazer o bloco dela ficou caro demais. São coisas
diferentes.

**Descoberta.** Um nó guarda a lista de quem conhece e troca essa lista com
quem encontra. Você apresenta ele a **um** par; o resto ele descobre
sozinho. Três nós, apresentando C só a B, e C aprende A na primeira
conversa. É só isso que "descentralizado" significa na prática.

## O no semente

```bash
curl https://web-production-a3ca95.up.railway.app/estado
python3 no.py conhecer https://web-production-a3ca95.up.railway.app
python3 no.py rodada
```

Um nó recém-instalado não conhece ninguém, e não existe jeito de
descobrir por conta própria quem está no ar. Então a lista começa escrita
no código, em `PARES_SEMENTE`. É a única parte de uma blockchain que não
é matemática: um endereço que alguém precisa manter de pé. O Bitcoin tem
cinco desses — os *DNS seeds* — e nunca conseguiu se livrar de nenhum.

Repara no que o nó semente **não** pode fazer. Não pode mentir sobre a
cadeia, porque a gênese é constante e a validação é integral: se mandar
outra história, ela é recusada por mais trabalho que traga. Não pode
inventar pares, porque quem ele indica se apresenta sozinho ou não é
falado com. Não pode gastar moeda de ninguém, porque não tem chave. O pior
que um nó semente consegue fazer é **não responder**.

E ele não precisa de backup. O sistema de arquivos do servidor é
efêmero: a cada deploy o nó perde `cadeia.json`, `pendentes.json` e
`pares.json`. Está certo assim — ele sobe, lê o `PARES_SEMENTE`, pede a
cadeia aos pares, e a validação decide. Foi isso que a gênese constante
comprou, e só aqui deu para ver o troco.

Para atender estranhos 24 horas faltavam coisas que um nó na sua mão
nunca precisou:

| | |
|---|---|
| `ThreadingHTTPServer` | um cliente lento travava todos os outros |
| tranca reentrante na cadeia e na fila | dois POST simultâneos liam o mesmo arquivo, e o último a gravar apagava a decisão do outro |
| teto de 8 MB no POST | um `Content-Length` mentiroso derrubava o processo por memória |
| gravação atômica (`.tmp` + `os.replace`) | `open(arquivo, "w")` trunca na hora: processo morto no meio de um deploy deixava um JSON cortado, e o nó não voltava a subir |
| rodada automática num fio de fundo | um nó que só escuta fica atrás e nunca descobre sozinho |
| número do ambiente lido sem `int()` cru | um `TEMPEST_RODADA=60=` derrubou o nó de verdade: um sinal de igual a mais, e o processo morria antes de abrir a porta |

A última linha custou um deploy para aparecer, e é a mais geral das seis.
Um programa que você roda na mão pode morrer com um erro na cara: você lê,
conserta, roda de novo. Um processo que atende sozinho num servidor não
tem esse luxo — cada jeito de morrer é um jeito de a rede sumir enquanto
ninguém olha. Mas ele também não deve adivinhar: tirar o `=` e supor que a
intenção era 60 seria pior, porque aí o nó roda com um valor que ninguém
escreveu. Ele avisa e segue com o padrão.

O nó semente **não minera**. Se minerasse, seria o único minerador e
ficaria com todas as moedas.

Um nó atrás de NAT — um celular, por exemplo — não deve se anunciar: não
tem endereço que os outros alcancem. Deixe o `sou` vazio e ele só procura,
sem prometer um endereço que não atende.

## A tela

```bash
python3 tela.py      # depois abra http://127.0.0.1:5050
```

A carteira no navegador: saldo, mineração, envio, emissão e a cadeia. Um
arquivo, sem CDN, sem fonte baixada, sem framework — funciona com o
aparelho em modo avião.

O herói da tela não é o saldo, é o hash do topo da cadeia com os zeros à
esquerda destacados. Aqueles zeros são a dificuldade, e são a única coisa
ali que custou alguma coisa. Carteira de verdade esconde isso; aqui é o
ponto.

`tela.py` é um programa separado do `no.py` de propósito. Estas rotas
assinam com a chave privada e mineram para o seu endereço, então o
servidor se amarra em `127.0.0.1` e recusa qualquer cliente que não seja a
própria máquina. O `no.py`, que atende a rede em `0.0.0.0`, não tem
nenhuma rota que toque na chave.

## A gênese é uma constante

```python
GENESE = {
    "indice": 0,
    "anterior": "4b21ebff…",   # sha256 do nome da rede
    "raiz":     "e3b0c442…",   # Merkle de lista vazia
    "quando":   1793577600,    # 2026-11-02T00:00:00Z
    "nonce":    42837,         # minerado uma vez, aqui, e nunca mais
    "hash":     "0000d4fd…",
}
```

Antes disso cada instalação minerava a própria gênese com o próprio
relógio, e duas máquinas nasciam com origens diferentes. A consequência
não era a rede se dividir — era pior: a validação só conferia o campo
`anterior`, então o nó com mais trabalho impunha a gênese dele e o outro
perdia em silêncio os blocos que tinha minerado.

Rede não se define por quem chega com mais trabalho. Define-se por uma
origem comum. A validação agora compara o bloco zero campo a campo com a
constante, e uma cadeia com outra gênese é recusada por mais trabalho que
traga.

## O cabeçalho é binário

88 bytes de tamanho fixo, big-endian: índice 8, anterior 32, raiz 32,
tempo 8, nonce 8. Sem `json`, sem ponto flutuante — o tempo é segundo
inteiro.

O motivo é consenso, não desempenho. Enquanto o hash saía de
`json.dumps`, a identidade de um bloco dependia de como o serializador de
uma linguagem escreve um número: o mesmo instante com uma casa decimal a
mais dava outro hash, e dois nós honestos discordariam sem ninguém ter
errado. Com campo de tamanho fixo, qualquer programa em qualquer
linguagem chega ao mesmo hash — dá para conferir com `sha256sum` sobre os
88 bytes crus, sem Python nenhum. As transações seguem a mesma regra: 84
bytes fixos é o que a assinatura protege — 32 da chave pública, 20 do
endereço, e quatro campos de 8.

## As assinaturas são Schnorr

```bash
python3 schnorr.py vetores   # os 19 vetores oficiais da BIP-340
python3 schnorr.py dois      # duas chaves somadas numa, e uma assinatura só
python3 schnorr.py ataque    # a chave forjada, e a defesa
```

A cadeia assinava com ECDSA e passou ao Schnorr da
[BIP-340](https://github.com/bitcoin/bips/blob/master/bip-0340.mediawiki),
o mesmo que o Bitcoin adotou no Taproot em 2021. Os 19 vetores oficiais
passam byte a byte, **incluindo os que têm que falhar** — chave fora da
curva, `s` acima da ordem do grupo, nonce de paridade errada. Essa metade
é a interessante: uma implementação que só aceita o que deve aceitar ainda
não foi testada.

A chave pública caiu de 64 bytes para 32. Só o `x` vai no bloco; dos dois
`y` possíveis a convenção escolhe o par, e quem confere o recalcula
resolvendo a equação da curva. Metade do espaço, nenhuma informação
perdida.

Mas o que o Schnorr tem e o ECDSA não tem é **linearidade**: somar duas
assinaturas dá uma assinatura válida da soma das duas chaves. É daqui que
sai a conta conjunta.

## A conta conjunta

```bash
python3 cadeia.py conjunta <chave pública do outro>
python3 cadeia.py enviar-conjunto <pasta do outro> <endereço> 40 3
```

Dois donos somam as chaves públicas, e o resultado é um endereço cuja
chave privada **não existe** — nem eles a conhecem. Gastar de lá exige os
dois assinando junto, e o que entra no bloco é uma chave de 32 bytes e uma
assinatura de 64, iguais às de um dono só. A cadeia não ganhou campo novo,
nem regra nova, e não tem como saber que a conta é de duas pessoas.

Somar as chaves direto, porém, é um buraco. Se o Bob espera a chave do
Alice e publica `Pb = x·G − Pa`, a soma vira `x·G` e ele assina sozinho
pelos dois. A defesa é a da MuSig: cada chave entra multiplicada por um
coeficiente que sai do hash da lista inteira, então ninguém pode escolher
a sua depois de ver as outras. O `schnorr.py ataque` roda o ataque com a
defesa e sem ela, lado a lado.

Duas honestidades sobre o escopo. O `enviar-conjunto` lê as duas chaves
privadas no mesmo processo, que é justamente o que na vida real não se faz:
cada dono guarda a sua numa máquina e o protocolo tem rodadas, nas quais os
nonces são trocados **antes** de qualquer assinatura parcial — senão quem
falar por último escolhe o nonce depois de ver os outros, que é o mesmo
padrão do ataque da chave forjada. E é 2-de-2, não k-de-n: não dá para
gastar faltando um.

## Quanto custa quebrar uma chave

```bash
python3 pollard.py curvas      # as curvas pequenas, conferidas na hora
python3 pollard.py rho 24      # quebra uma chave e conta os passos
python3 pollard.py lei         # passos / raiz(n): a constante aparece
python3 pollard.py canguru     # na secp256k1 de verdade
python3 pollard.py conta       # a extrapolacao para 256 bits
```

A chave privada é um número `k`; a pública é o ponto `Q = k·G`. Quebrar
a chave é achar `k` tendo `Q`. Força bruta custa `n` tentativas, onde `n`
é a ordem do grupo. **Pollard rho custa a raiz de `n`** — e essa raiz é a
resposta para uma pergunta que quase ninguém faz: por que 256 bits, e não
128? Porque o melhor ataque conhecido precisa de 2¹²⁸ passos contra uma
chave de 256 bits. **A secp256k1 tem chave de 256 bits e segurança de
128.** Metade do número não é desperdício, é o preço do rho.

O passeio guarda um par `(a, b)` com `X = a·G + b·Q` e anda somando um de
32 saltos sorteados, escolhido pelo próprio `X`. Quando dois pontos do
passeio coincidem, duas combinações diferentes de `(a, b)` dão o mesmo
ponto, e aí:

```
a1 + b1·k = a2 + b2·k   (mod n)
k = (a1 - a2) / (b2 - b1)
```

Nenhum palpite sobre `k`, nenhuma busca. Só o fato de o passeio não ter
para onde fugir: num grupo de `n` elementos bastam uns `√(πn/2)` pontos
para dois coincidirem — o paradoxo do aniversário.

O `lei` mede isso. Repete o rho em quatro ordens, de 16 a 28 bits, e
divide os passos pela raiz. A constante **1,2533** aparece sozinha na
última coluna, sem nunca ter sido escrita no código. Ela cambaleia, porque
o rho é probabilístico; o expoente não cambaleia nada.

### Na curva do Bitcoin

O `canguru` é o Pollard lambda, e roda na secp256k1 **de verdade** — mesmo
`G`, mesmos 256 bits. O que muda é a chave: sorteada dentro de um
intervalo de 28 bits, como numa carteira feita com relógio como semente.
Dois cangurus pulam para a frente com passos que dependem só de onde cada
um está; quando o selvagem pisa numa pegada do manso, passa a seguir o
mesmo caminho, e a diferença das distâncias percorridas é a chave.

Num celular: **268 milhões de chaves possíveis, resolvidas em 7 segundos
e 30 mil somas de ponto**, sem testar nenhuma delas.

E aqui está o detalhe fino, que fecha o laço com a semente de doze
palavras. O rho e o canguru só economizam a raiz quando o espaço tem
estrutura aditiva: um grupo inteiro, ou um trecho contínuo. As doze
palavras não têm — a PBKDF2 espalha os 2¹²⁸ candidatos pelo grupo sem
relação aditiva entre eles, e sem estrutura não há atalho: o atacante
testa um por um. Doze palavras valem 128 bits de segurança de verdade,
não 64 — e é exatamente o nível da própria curva. Mais entropia na frase
não compraria nada, porque o rho já limita o outro lado a 2¹²⁸. A BIP-39
não escolheu 128 bits por acaso.

O que quebra na prática é o contrário: chave num intervalo. É o que são
os "puzzles" do Bitcoin, e é por isso que eles vão sendo varridos conforme
a fronteira de bits avança.

### A conta

O `conta` mede as somas de ponto por segundo **nesta máquina** e
extrapola. Num celular, 4.900 por segundo:

| | |
|---|---|
| passos que o rho precisa | 4,27 × 10³⁸ |
| tempo neste aparelho | 2,75 × 10²⁷ anos |
| idade do universo | 1,38 × 10¹⁰ anos |
| a rede inteira do Bitcoin, se cada hash fosse uma soma de ponto | 1,1 vez a idade do universo |

A última linha é a que vale guardar. A segurança de uma assinatura da
secp256k1 não é "difícil": é todo o poder de cálculo que a humanidade já
apontou para uma coisa só, rodando desde o Big Bang, e ainda não acabou.
Nada disso depende de a curva ser bem feita, de o Bitcoin ser popular ou
de haver dinheiro em jogo. É a raiz quadrada.

## A semente em pedaços

```bash
python3 partilha.py repartir 3 5
python3 partilha.py juntar <pedaço> <pedaço> <pedaço>
python3 partilha.py provar
```

Partilha de Shamir sobre o corpo finito de 2^128 + 51, o menor primo
acima dos 128 bits de entropia das doze palavras. O segredo vira o termo
constante de um polinômio de grau k-1, e os pedaços são pontos da curva:
k pontos determinam o polinômio, k-1 não determinam nada.

E "nada" aqui é literal. Com k-1 pedaços, para cada segredo possível
existe exatamente um polinômio que passa por aqueles pontos com aquele
segredo — todos igualmente compatíveis. Não falta poder de cálculo,
falta informação. `provar` mostra isso acontecendo com números.

## A semente de doze palavras

A chave privada é um número de 256 bits. Perder o arquivo que a guarda é
perder as moedas, sem atendimento e sem recuperação — e um número desses
não se copia à mão sem errar um dígito.

```bash
python3 cadeia.py semente                  # mostra as 12 palavras
python3 cadeia.py restaurar "as doze ..."  # refaz a carteira a partir delas
```

É a [BIP-39](https://github.com/bitcoin/bips/blob/master/bip-0039/bip-0039-wordlists.md)
de verdade, implementada aqui e **conferida contra a implementação de
referência da Trezor** em 300 frases aleatórias, em todos os tamanhos de
entropia e com senha: idênticas, frase e semente.

Doze palavras de uma lista de 2048 carregam 132 bits — 128 de aleatoriedade
e 4 de soma de verificação. Esses 4 bits são o detalhe esperto: se você
copiar uma palavra errada, a frase não fecha e o programa avisa, em vez de
te entregar uma carteira vazia e silenciosa. E as quatro primeiras letras
de cada palavra da lista já são únicas entre as 2048 — dá para anotar só
quatro letras e não haver dúvida.

A lista (`palavras.txt`) é a oficial em português, baixada do repositório
das BIPs. Se quiser conferir: `md5sum palavras.txt` deve dar
`05ee6fde129776830351bbacd5b0dcfb`.

Daqui as carteiras de verdade seguem para a BIP-32, que deriva uma árvore
infinita de chaves a partir da mesma semente, e é por isso que elas dão um
endereço novo a cada recebimento. Aqui a semente gera **uma** chave. O
backup funciona igual; a privacidade de vários endereços não está
implementada.

## Como a moeda funciona

| | |
|---|---|
| Intervalo alvo entre blocos | 5 segundos |
| Revisão da dificuldade | a cada 10 blocos |
| Recompensa inicial | 50 TEMP |
| Halving | a cada 20 blocos |
| Teto total | 1890 TEMP |
| Último bloco com recompensa | 119 |
| Taxa | definida por quem envia, vai para quem minera |

```bash
python3 cadeia.py emissao
```

Os números são pequenos de propósito: você vê um halving acontecer em
minutos, e a emissão terminar numa tarde. No Bitcoin o halving é a cada
quatro anos e a emissão termina em 2140 — a mesma curva, numa escala que
ninguém vive para ver inteira.

Depois do bloco 119 a recompensa é zero e **só as taxas** pagam a
mineração. É o problema de longo prazo de qualquer moeda com teto, e aqui
ele acontece rápido o suficiente para você observar.

## Os arquivos

| | |
|---|---|
| `curva.py` | secp256k1 à mão: soma de pontos, multiplicação escalar, endereço |
| `schnorr.py` | a assinatura da BIP-340 e a soma de chaves da MuSig |
| `pollard.py` | o rho e o canguru: quanto custa quebrar uma chave |
| `cadeia.py` | blocos, transações, Merkle, dificuldade, emissão, validação, CLI |
| `no.py` | o nó HTTP, o consenso, a reorganização e a descoberta de pares |
| `semente.py` | BIP-39: entropia → doze palavras → chave |
| `tela.py` | a carteira no navegador, servida só para a própria máquina |
| `partilha.py` | partilha de Shamir: a semente em pedaços |
| `palavras.txt` | a lista oficial de 2048 palavras em português |

Estado em disco, tudo ignorado pelo git:

| | |
|---|---|
| `cadeia.json` | a cadeia |
| `carteira.json` | **a chave privada e a frase.** Nunca publique, nunca cole em lugar nenhum |
| `pendentes.json` | a fila de transações |
| `pares.json` | quem este nó conhece |

## O que não está aqui

Para não haver ilusão sobre o escopo:

- **Carteira leve.** A prova de inclusão de Merkle existe
  (`python3 cadeia.py prova <bloco> <n>`), que é a peça que uma carteira
  leve usa, mas não há cliente que viva só dela.
- **BIP-32.** Uma chave por semente, não uma árvore.
- **Scripts e contratos.** As transações só transferem valor.
- **Privacidade.** Os endereços são públicos e ligáveis, como no Bitcoin.
- **Rede robusta.** Existe um nó semente no ar, mas é **um**, mantido por
  uma pessoa, num plano gratuito. Rede de verdade tem vários, em máquinas
  e jurisdições diferentes, e nenhum deles indispensável.

## Por que isso existe

O código do Bitcoin é público desde 2009 e foi copiado milhares de vezes.
Existem milhares de moedas que são o Bitcoin com o nome trocado, e quase
todas valem zero. Se escrever o código fosse a parte difícil, qualquer um
seria rico.

Escrever o código é a parte fácil. Dois dias, num celular. O que não é
fácil é o resto: milhares de máquinas independentes recusando
simultaneamente a mesma mentira, e gente disposta a trocar algo real por
aquilo. O Tempest tem o código inteiro e nada do resto, e serve justamente
para deixar essa diferença impossível de não ver.

## Licença

MIT. Faça o que quiser, inclusive usar em aula.
