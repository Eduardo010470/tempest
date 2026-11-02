# Tempest

Uma blockchain escrita do zero em Python, sem nenhuma dependência externa.
Roda num celular Android, dentro do Termux, em 1225 linhas.

O `pip install` nunca foi chamado neste projeto. Só a biblioteca padrão do
Python: `hashlib`, `hmac`, `json`, `secrets`, `http.server`. A curva
elíptica, a assinatura digital, a árvore de Merkle e a derivação da semente
de doze palavras estão escritas aqui, à mão.

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
| `curva.py` | secp256k1 à mão: soma de pontos, multiplicação escalar, ECDSA |
| `cadeia.py` | blocos, transações, Merkle, dificuldade, emissão, validação, CLI |
| `no.py` | o nó HTTP, o consenso, a reorganização e a descoberta de pares |
| `semente.py` | BIP-39: entropia → doze palavras → chave |
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
- **Rede pública.** Os nós se descobrem entre si, mas não há nó semente
  inicial no ar em lugar nenhum.

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
