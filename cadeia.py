# -*- coding: utf-8 -*-
"""Tempest (TEMP) — uma blockchain minima, mas honesta.

O que ela tem:

  - transacoes assinadas na secp256k1, a mesma curva do Bitcoin
  - blocos encadeados por hash: mexer no passado quebra o futuro
  - prova de trabalho com DIFICULDADE AJUSTAVEL, recalculada pela propria
    cadeia, de modo que todo no chega ao mesmo numero sem combinar nada
  - EMISSAO LIMITADA: a recompensa cai pela metade a cada halving e
    chega a zero. Existe um teto de moedas, e ele e calculavel.
  - TAXA por transacao, que vai para quem minera o bloco. E o que
    sustenta a rede depois que a emissao acaba.
  - validacao independente: um no confere tudo do zero, sozinho
  - saldo derivado do historico, nunca guardado num campo

E tres defesas contra quem NAO e honesto, que e o unico caso que importa:

  - SEQUENCIA por remetente, que torna impossivel repetir uma transacao
    assinada. Sem isso, qualquer um que visse a sua transacao podia
    reenviar a mesma e drenar a sua conta de novo.
  - RELOGIO LIMITADO: o minerador nao pode mentir sobre a hora para
    baratear a prova de trabalho. Ha um piso (a mediana dos ultimos
    blocos) e um teto (o futuro proximo).
  - RAIZ DE MERKLE no cabecalho, em vez da lista de transacoes crua.
    O bloco passa a cabar numa impressao digital de 32 bytes, e da para
    provar que uma transacao esta nele sem baixar as outras.

Uso:
    python3 cadeia.py carteira
    python3 cadeia.py minerar
    python3 cadeia.py saldo [endereco]
    python3 cadeia.py enviar <endereco> <valor> [taxa]
    python3 cadeia.py pendentes
    python3 cadeia.py cadeia
    python3 cadeia.py emissao
    python3 cadeia.py validar
    python3 cadeia.py semente               mostra as doze palavras
    python3 cadeia.py restaurar "<frase>"   refaz a carteira a partir delas
    python3 cadeia.py prova <bloco> <n>     prova que a tx n esta no bloco
    python3 cadeia.py adulterar <bloco>     ataque 1: mexer no passado
    python3 cadeia.py repetir               ataque 2: reenviar uma tx antiga
    python3 cadeia.py atrasar               ataque 3: mentir no relogio
"""
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import curva
import schnorr
import semente

NOME = "Tempest"
SIMBOLO = "TEMP"

ALVO_SEGUNDOS = 5        # intervalo desejado entre blocos
JANELA = 10              # de quantos em quantos blocos a dificuldade e revista
DIF_INICIAL = 4
DIF_MIN, DIF_MAX = 3, 7

RECOMPENSA_INICIAL = 50
HALVING = 20             # a cada 20 blocos a recompensa cai pela metade

MEDIANA_N = 11           # quantos blocos entram na mediana do relogio
FUTURO_MAX = 30          # quantos segundos adiantado um bloco pode estar

ARQ_CADEIA = "cadeia.json"
ARQ_CARTEIRA = "carteira.json"
ARQ_PENDENTES = "pendentes.json"


# ---------------------------------------------------------------- carteira

def grava_carteira(frase):
    """Escreve a carteira derivada da frase de doze palavras."""
    priv = semente.chave_de(frase)
    pub = schnorr.publica(priv)          # 32 bytes, x-only (BIP-340)
    end = curva.endereco(pub)
    grava(ARQ_CARTEIRA, {"frase": frase, "priv": "%064x" % priv,
                         "pub": pub.hex(), "endereco": end}, segredo=True)
    return priv, pub, end


def carrega_carteira():
    """Devolve (priv, pub, endereco, frase_recem_criada_ou_None)."""
    if os.path.exists(ARQ_CARTEIRA):
        d = json.load(open(ARQ_CARTEIRA))
        if len(d["pub"]) != 64:
            # carteira de antes do Schnorr: a chave publica tinha 64 bytes
            # (x e y) e agora tem 32 (so o x). A chave PRIVADA nao muda, e
            # a frase tambem nao — so o que se deriva delas. Refaco em vez
            # de seguir com um arquivo que nao casa mais com o codigo.
            if "frase" not in d:
                raise SystemExit(
                    "esta carteira e de antes do Schnorr e nao tem frase de\n"
                    "doze palavras para refazer a chave publica. mova o\n"
                    "%s de lado e crie outra." % ARQ_CARTEIRA)
            antigo = d["endereco"]
            priv, pub, end = grava_carteira(d["frase"])
            print("carteira atualizada para Schnorr: a chave publica caiu de")
            print("64 para 32 bytes e o endereco mudou junto.")
            print("  antes:", antigo)
            print("  agora:", end, "\n")
            return priv, pub, end, None
        return (int(d["priv"], 16), bytes.fromhex(d["pub"]), d["endereco"],
                None)
    frase = semente.gera_frase()
    priv, pub, end = grava_carteira(frase)
    return priv, pub, end, frase


# ---------------------------------------------------- emissao e dificuldade

def recompensa_em(indice):
    """Quanto o bloco `indice` pode criar do nada. Cai pela metade e zera."""
    return RECOMPENSA_INICIAL >> (indice // HALVING)


def teto():
    """Total de moedas que a rede vai criar ate o fim dos tempos."""
    t, i = 0, 1
    while True:
        r = recompensa_em(i)
        if r == 0:
            return t
        t += r
        i += 1


def dificuldade_em(cadeia, indice):
    """Dificuldade exigida do bloco `indice`, deduzida so do passado.

    Todo no calcula isso sozinho e chega ao mesmo numero. Nao existe
    autoridade dizendo qual e a dificuldade — ela esta implicita na cadeia.
    """
    d = DIF_INICIAL
    marco = JANELA
    while marco <= indice:
        gasto = cadeia[marco - 1]["quando"] - cadeia[marco - JANELA]["quando"]
        esperado = ALVO_SEGUNDOS * (JANELA - 1)
        if gasto < esperado / 2.0 and d < DIF_MAX:
            d += 1
        elif gasto > esperado * 2.0 and d > DIF_MIN:
            d -= 1
        marco += JANELA
    return d


# ------------------------------------------------------------- o relogio

def tempo_mediano(cadeia, indice):
    """A mediana do relogio dos blocos anteriores a `indice`.

    Existe porque a dificuldade e calculada em cima de horarios, e os
    horarios sao escritos pelo proprio minerador. Sem um piso, bastava
    datar o bloco no passado para a janela parecer longa e a dificuldade
    cair — mineracao barata a custa de uma mentira. A mediana de onze
    blocos nao se move com um bloco mentiroso: para empurra-la, o
    atacante precisa ja ter a maioria da rede, e nesse caso ele tem
    problemas piores para nos dar. E o mesmo remedio do Bitcoin.
    """
    if indice == 0:
        return 0
    janela = sorted(int(b["quando"]) for b in
                    cadeia[max(0, indice - MEDIANA_N):indice])
    return janela[len(janela) // 2]


# ------------------------------------------------------------- transacoes

def corpo_tx(tx):
    """Os bytes exatos que a assinatura protege. 116 bytes, sempre.

    NAO use json aqui. A forma canonica de uma transacao nao pode depender
    de como o serializador de uma linguagem escreve um numero: outro
    programa, em outra lingua, produziria bytes diferentes para a mesma
    transacao e calcularia outro hash. Campo de tamanho fixo, big-endian,
    e a mesma coisa em qualquer maquina que saiba contar.
    """
    return (bytes.fromhex(tx["de"])                    # 64: a chave publica
            + bytes.fromhex(tx["para"])                # 20: o endereco
            + tx["valor"].to_bytes(8, "big")
            + tx["taxa"].to_bytes(8, "big")
            + tx["seq"].to_bytes(8, "big")
            + int(tx["quando"]).to_bytes(8, "big"))


def id_tx(tx):
    """A impressao digital da transacao inteira, assinatura incluida.

    O primeiro byte diz o tipo, para que uma recompensa nunca possa ser
    confundida com uma transacao assinada por mais parecidos que sejam os
    campos restantes.
    """
    if tx["de"] is None:
        corpo = (b"\x00"
                 + bytes.fromhex(tx["para"])
                 + tx["valor"].to_bytes(8, "big")
                 + int(tx["quando"]).to_bytes(8, "big"))
    else:
        corpo = b"\x01" + corpo_tx(tx) + bytes.fromhex(tx["assinatura"])
    return hashlib.sha256(corpo).hexdigest()


def cria_tx(priv, pub, para, valor, taxa, seq):
    tx = {"de": pub.hex(), "para": para, "valor": valor, "taxa": taxa,
          "seq": seq, "quando": int(time.time())}
    tx["assinatura"] = schnorr.assina(priv, corpo_tx(tx)).hex()
    return tx


def tx_valida(tx):
    if tx.get("de") is None:
        return False                           # a recompensa tem regra propria
    if tx["valor"] <= 0 or tx["taxa"] < 0:
        return False
    if not isinstance(tx.get("seq"), int) or tx["seq"] < 0:
        return False
    pub = bytes.fromhex(tx["de"])
    if len(pub) != 32:
        return False
    if curva.endereco(pub) == tx["para"]:
        return False
    # Schnorr, nao ECDSA. Para a cadeia nao muda nada: 64 bytes de
    # assinatura contra 32 de chave. Mas essa chave pode ser a SOMA de
    # varias, e quem confere nao tem como saber — e e exatamente por isso
    # que a conta conjunta nao precisa de campo novo no bloco.
    return schnorr.confere(pub, corpo_tx(tx), bytes.fromhex(tx["assinatura"]))


def remetente(tx):
    return None if tx["de"] is None else curva.endereco(bytes.fromhex(tx["de"]))


def sequencias(cadeia):
    """Quantas transacoes cada endereco ja gastou.

    Esse numero E a defesa contra repeticao. A assinatura de uma
    transacao e eterna: quem a viu passar pode guardar e reenviar
    quantas vezes quiser. Mas ela carrega, assinado junto, o numero de
    ordem dela na vida do remetente — e esse numero so serve uma vez.
    A segunda tentativa chega com um numero ja gasto e e recusada.
    """
    q = {}
    for b in cadeia:
        for tx in b["transacoes"]:
            de = remetente(tx)
            if de is not None:
                q[de] = q.get(de, 0) + 1
    return q


# ------------------------------------------------------------------ merkle

def raiz_merkle(txs):
    """Reduz a lista de transacoes a um unico hash de 32 bytes.

    Poe as transacoes como folhas, junta de duas em duas, e sobe ate
    sobrar uma. Mudar um centavo em qualquer folha muda a raiz, e a raiz
    e o que entra no cabecalho do bloco. Dai vem o troco que o Bitcoin
    tira disso: para provar que uma transacao esta no bloco nao e preciso
    ter as outras — bastam os hashes irmaos do caminho dela ate o topo,
    que sao log2(n). Num bloco de mil transacoes, dez hashes.
    """
    if not txs:
        return hashlib.sha256(b"").hexdigest()
    nivel = [id_tx(t) for t in txs]
    while len(nivel) > 1:
        if len(nivel) % 2:
            nivel.append(nivel[-1])
        nivel = [hashlib.sha256((nivel[k] + nivel[k + 1]).encode()).hexdigest()
                 for k in range(0, len(nivel), 2)]
    return nivel[0]


def prova_merkle(txs, n):
    """O caminho de hashes irmaos que leva txs[n] ate a raiz."""
    nivel = [id_tx(t) for t in txs]
    caminho, i = [], n
    while len(nivel) > 1:
        if len(nivel) % 2:
            nivel.append(nivel[-1])
        irmao = i ^ 1
        caminho.append({"lado": "direita" if irmao > i else "esquerda",
                        "hash": nivel[irmao]})
        nivel = [hashlib.sha256((nivel[k] + nivel[k + 1]).encode()).hexdigest()
                 for k in range(0, len(nivel), 2)]
        i //= 2
    return caminho


def confere_prova(identificador, caminho, raiz):
    """Refaz o caminho de baixo para cima e ve se chega na raiz."""
    h = identificador
    for passo in caminho:
        junto = ((h + passo["hash"]) if passo["lado"] == "direita"
                 else (passo["hash"] + h))
        h = hashlib.sha256(junto.encode()).hexdigest()
    return h == raiz


# ----------------------------------------------------------------- blocos

CABECALHO = 88          # 8 + 32 + 32 + 8 + 8


def cabecalho_bytes(b):
    """Os 88 bytes que a prova de trabalho protege. Sem json, sem float.

    indice 8 | anterior 32 | raiz 32 | quando 8 | nonce 8

    O tempo e segundo inteiro, nao ponto flutuante: o mesmo instante
    escrito com uma casa decimal a mais daria outro hash, e dois nos
    honestos discordariam sem ninguem ter errado.
    """
    return (b["indice"].to_bytes(8, "big")
            + bytes.fromhex(b["anterior"])
            + bytes.fromhex(b["raiz"])
            + int(b["quando"]).to_bytes(8, "big")
            + b["nonce"].to_bytes(8, "big"))


def hash_bloco(b):
    return hashlib.sha256(cabecalho_bytes(b)).hexdigest()


def minera_bloco(indice, anterior, transacoes, dificuldade, piso=0):
    agora = int(time.time())
    if agora <= piso:
        agora = piso + 1              # respeita o piso do relogio
    b = {"indice": indice, "anterior": anterior, "quando": agora,
         "raiz": raiz_merkle(transacoes), "transacoes": transacoes, "nonce": 0}
    alvo = "0" * dificuldade
    while True:
        h = hash_bloco(b)
        if h.startswith(alvo):
            b["hash"] = h
            return b
        b["nonce"] += 1


# A GENESE E UMA CONSTANTE, nao um bloco minerado na hora.
#
# Antes disso cada maquina minerava a propria genese com o relogio dela,
# e duas instalacoes nasciam com geneses diferentes. A consequencia nao
# era a rede se dividir — era pior: `valida` so conferia o campo
# `anterior`, entao o no com mais trabalho impunha a genese dele e o
# outro perdia os blocos que tinha minerado, sem aviso.
#
# Rede nao e definida por quem chega com mais trabalho. E definida por
# uma origem comum. No Bitcoin a genese e uma constante no codigo-fonte
# desde 2009, e uma cadeia com outra genese e recusada por mais trabalho
# que traga. Aqui tambem, agora.
#
# O campo `anterior`, onde nao ha bloco anterior para apontar, guarda o
# sha256 do nome da rede. Satoshi usou esse espaco para a manchete do
# Times de 3 de janeiro de 2009.
GENESE = {
    "indice": 0,
    "anterior": "4b21ebff52639c9be4e81a54c99e17beb900b626e86bb482be1c06016b5d02b4",
    "raiz": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "quando": 1793577600,          # 2026-11-02T00:00:00Z
    "nonce": 42837,                # minerado uma vez, aqui, e nunca mais
    "transacoes": [],
    "hash": "0000d4fd8d4447688c6088930c5ed25c3eea7cba7098f2f470115a7da9239492",
}


def genesis():
    """Devolve a genese da rede. Igual em toda maquina, sempre."""
    return json.loads(json.dumps(GENESE))


# ----------------------------------------------------------------- cadeia

def carrega_cadeia():
    if os.path.exists(ARQ_CADEIA):
        return json.load(open(ARQ_CADEIA))
    c = [genesis()]
    grava_cadeia(c)
    return c


def grava(arquivo, dado, segredo=False):
    """Grava trocando o arquivo, nunca escrevendo em cima dele.

    `open(arquivo, "w")` trunca na hora. Se o processo morrer no meio —
    deploy, falta de memoria, bateria — o que sobra no disco e um json
    cortado, e o proximo json.load levanta erro. Um no que atende 24
    horas morre assim e nao volta a subir sozinho.

    Gravar num .tmp e trocar com os.replace e atomico no sistema de
    arquivos: ou o arquivo antigo esta inteiro, ou o novo esta inteiro,
    nunca um pedaco dos dois. E o mesmo cuidado dos patches deste
    repositorio, pelo mesmo motivo.

    Com segredo=True o arquivo NASCE 600. Antes a carteira era criada
    com a permissao padrao e so depois virava 600 — havia um instante,
    curto mas real, em que a chave privada estava legivel para qualquer
    usuario da maquina.
    """
    tmp = arquivo + ".tmp"
    if segredo:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        f = os.fdopen(fd, "w", encoding="utf-8")
    else:
        f = open(tmp, "w", encoding="utf-8")
    with f:
        json.dump(dado, f, indent=1)
    os.replace(tmp, arquivo)


def grava_cadeia(c):
    grava(ARQ_CADEIA, c)


def carrega_pendentes():
    if os.path.exists(ARQ_PENDENTES):
        return json.load(open(ARQ_PENDENTES))
    return []


def grava_pendentes(p):
    grava(ARQ_PENDENTES, p)


def saldos(cadeia):
    s = {}
    for b in cadeia:
        for tx in b["transacoes"]:
            de = remetente(tx)
            if de is not None:
                s[de] = s.get(de, 0) - tx["valor"] - tx["taxa"]
            s[tx["para"]] = s.get(tx["para"], 0) + tx["valor"]
    return s


def valida(cadeia):
    """Confere a cadeia inteira do zero. Devolve (ok, motivo)."""
    if not cadeia:
        return False, "cadeia vazia"
    # A genese e conferida campo a campo contra a constante. Nao basta o
    # `anterior` bater: o bloco zero inteiro tem que ser EXATAMENTE este,
    # ou a cadeia e de outra rede e nao interessa quanto trabalho carrega.
    g = cadeia[0]
    for campo in ("indice", "anterior", "raiz", "quando", "nonce", "hash"):
        if g.get(campo) != GENESE[campo]:
            return False, ("a genese desta cadeia e de outra rede "
                           "(difere em '%s')" % campo)
    if g.get("transacoes") != []:
        return False, "a genese nao pode ter transacoes"
    agora = int(time.time())
    s, q = {}, {}
    for i, b in enumerate(cadeia):
        if b["indice"] != i:
            return False, "bloco %d com indice errado" % i
        if b.get("raiz") != raiz_merkle(b["transacoes"]):
            return False, ("bloco %d tem raiz de Merkle que nao corresponde "
                           "as transacoes" % i)
        if hash_bloco(b) != b["hash"]:
            return False, "bloco %d tem hash que nao corresponde ao cabecalho" % i
        exigida = dificuldade_em(cadeia, i)
        if not b["hash"].startswith("0" * exigida):
            return False, ("bloco %d nao cumpre a prova de trabalho exigida "
                           "(%d zeros)" % (i, exigida))
        if i > 0:
            if b["anterior"] != cadeia[i - 1]["hash"]:
                return False, "bloco %d nao aponta para o bloco anterior" % i
            piso = tempo_mediano(cadeia, i)
            if b["quando"] <= piso:
                return False, ("bloco %d esta datado antes da mediana dos "
                               "blocos anteriores" % i)
            if b["quando"] > agora + FUTURO_MAX:
                return False, "bloco %d esta datado no futuro" % i

        coinbase, taxas = None, 0
        for tx in b["transacoes"]:
            de = remetente(tx)
            if de is None:
                if coinbase is not None:
                    return False, "bloco %d tem mais de uma recompensa" % i
                coinbase = tx
                continue
            if not tx_valida(tx):
                return False, "bloco %d tem transacao com assinatura invalida" % i
            if tx["seq"] != q.get(de, 0):
                return False, ("bloco %d tem transacao com sequencia %d quando "
                               "a esperada era %d — repeticao ou fora de ordem"
                               % (i, tx["seq"], q.get(de, 0)))
            custo = tx["valor"] + tx["taxa"]
            if s.get(de, 0) < custo:
                return False, "bloco %d gasta saldo que nao existe" % i
            q[de] = q.get(de, 0) + 1
            s[de] = s.get(de, 0) - custo
            s[tx["para"]] = s.get(tx["para"], 0) + tx["valor"]
            taxas += tx["taxa"]

        if coinbase is not None:
            devido = recompensa_em(i) + taxas
            if coinbase["valor"] != devido:
                return False, ("bloco %d paga %d ao minerador mas devia pagar %d"
                               % (i, coinbase["valor"], devido))
            s[coinbase["para"]] = s.get(coinbase["para"], 0) + coinbase["valor"]
        elif i > 0 and recompensa_em(i) + taxas > 0:
            return False, "bloco %d nao paga o minerador" % i

    return True, "cadeia integra, %d blocos" % len(cadeia)


# -------------------------------------------------------------------- cli

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "ajuda"

    if cmd == "restaurar":
        frase = " ".join(sys.argv[2:])
        if not frase:
            print('uso: python3 cadeia.py restaurar "as doze palavras"')
            return
        ok, motivo = semente.confere_frase(frase)
        print(("frase conferida: " if ok else "frase recusada: ") + motivo)
        if not ok:
            print("nada foi tocado.")
            return
        if os.path.exists(ARQ_CARTEIRA):
            reserva = ARQ_CARTEIRA.replace(".json", "-anterior.json")
            os.replace(ARQ_CARTEIRA, reserva)
            print("a carteira que estava aqui foi guardada em", reserva)
        _, _, end = grava_carteira(semente.normaliza(frase))
        print("carteira restaurada.")
        print("endereco:", end)
        print("saldo:   ", saldos(carrega_cadeia()).get(end, 0), SIMBOLO)
        print("\nse o endereco nao e o que voce esperava, a frase esta certa")
        print("mas nao e a dessa carteira — a sua anterior continua no")
        print("arquivo de reserva.")
        return

    priv, pub, eu, nova = carrega_carteira()
    cadeia = carrega_cadeia()

    if nova:
        print("=" * 64)
        print("CARTEIRA NOVA. Estas sao as doze palavras dela:\n")
        print("   " + nova)
        print("\nCopie num papel, agora, e guarde fora do telefone. Elas")
        print("reconstroem esta carteira em qualquer maquina, e quem as tiver")
        print("tem as moedas. Nao ha segunda via: se o arquivo sumir e voce")
        print("nao tiver as palavras, as moedas ficam na cadeia para sempre,")
        print("visiveis e inalcancaveis.")
        print("=" * 64 + "\n")

    if cmd == "semente":
        d = json.load(open(ARQ_CARTEIRA))
        if "frase" not in d:
            print("esta carteira foi criada antes da semente existir, e por")
            print("isso nao tem frase: a chave dela foi sorteada direto, e o")
            print("caminho da frase para a chave nao volta.")
            print("\no unico backup dela e copiar o proprio", ARQ_CARTEIRA)
            print("\npara ter uma carteira com as doze palavras, tire esta do")
            print("caminho e rode 'carteira' — o endereco sera outro:")
            print("   mv %s carteira-antiga.json" % ARQ_CARTEIRA)
            return
        print("as doze palavras desta carteira:\n")
        print("   " + d["frase"])
        print("\nendereco:", d["endereco"])
        print("\nqualquer pessoa que leia isto na sua tela fica com as moedas.")

    elif cmd == "carteira":
        print("rede:    ", NOME, "(%s)" % SIMBOLO)
        print("endereco:", eu)
        print("saldo:   ", saldos(cadeia).get(eu, 0), SIMBOLO)
        print("sequencia:", sequencias(cadeia).get(eu, 0),
              "- numero da proxima transacao que vou assinar")
        d = json.load(open(ARQ_CARTEIRA))
        if "frase" in d:
            print("\nbackup: doze palavras, em 'cadeia.py semente'")
        else:
            print("\nbackup: nenhum alem do proprio", ARQ_CARTEIRA)
        print("a chave privada esta nesse arquivo - quem tem ela tem as moedas")

    elif cmd == "saldo":
        alvo = sys.argv[2] if len(sys.argv) > 2 else eu
        print(alvo, "->", saldos(cadeia).get(alvo, 0), SIMBOLO)

    elif cmd == "enviar":
        para, valor = sys.argv[2], int(sys.argv[3])
        taxa = int(sys.argv[4]) if len(sys.argv) > 4 else 1
        pend = carrega_pendentes()
        gasto = sum(t["valor"] + t["taxa"] for t in pend if remetente(t) == eu)
        if saldos(cadeia).get(eu, 0) - gasto < valor + taxa:
            print("saldo insuficiente para", valor, "+", taxa, "de taxa")
            if gasto:
                print("(ja tenho %d comprometido na fila)" % gasto)
            return
        # a sequencia continua de onde a fila parou, senao duas transacoes
        # seguidas nasceriam com o mesmo numero e a segunda seria recusada
        seq = (sequencias(cadeia).get(eu, 0)
               + sum(1 for t in pend if remetente(t) == eu))
        pend.append(cria_tx(priv, pub, para, valor, taxa, seq))
        grava_pendentes(pend)
        print("transacao %d assinada e na fila (%d %s + %d de taxa)."
              % (seq, valor, SIMBOLO, taxa))
        print("quem minerar o proximo bloco fica com a taxa.")

    elif cmd == "conjunta":
        if len(sys.argv) < 3:
            print("uso: python3 cadeia.py conjunta <chave publica do outro>")
            print("\na sua, para mandar para ele:")
            print("   " + pub.hex())
            return
        outra = bytes.fromhex(sys.argv[2])
        if len(outra) != 32:
            print("uma chave publica do Tempest tem 32 bytes (64 hex)."); return
        qx, _, _ = schnorr.agrega([pub, outra])
        end = curva.endereco(qx)
        print("sua chave:   ", pub.hex())
        print("a dele:      ", outra.hex())
        print("conjunta:    ", qx.hex())
        print("endereco:    ", end)
        print("saldo:       ", saldos(cadeia).get(end, 0), SIMBOLO)
        print("\nNinguem conhece a chave privada desse endereco — ela nao")
        print("existe. Gastar de la exige os dois assinando junto, e a")
        print("cadeia nao tem como saber que sao dois: o que ela ve e uma")
        print("chave de 32 bytes e uma assinatura de 64, como qualquer outra.")

    elif cmd == "enviar-conjunto":
        if len(sys.argv) < 5:
            print("uso: python3 cadeia.py enviar-conjunto <pasta do outro> "
                  "<endereco> <valor> [taxa]")
            print("\nA pasta do outro e onde esta o carteira.json dele.")
            return
        pasta, para, valor = sys.argv[2], sys.argv[3], int(sys.argv[4])
        taxa = int(sys.argv[5]) if len(sys.argv) > 5 else 1
        arq = os.path.join(pasta, ARQ_CARTEIRA)
        if not os.path.exists(arq):
            print("nao achei", arq); return
        # ESTA e a parte artificial desta demonstracao: as duas chaves
        # privadas num processo so. Na vida real cada dono tem a sua numa
        # maquina diferente e o protocolo tem rodadas — e a ORDEM das
        # rodadas e o que importa: os nonces tem que ser trocados ANTES de
        # qualquer assinatura parcial, senao quem falar por ultimo escolhe
        # o proprio nonce depois de ver os outros e forja a assinatura do
        # grupo. E o mesmo padrao do ataque da chave forjada.
        outro = json.load(open(arq))
        priv_b = int(outro["priv"], 16)
        pub_b = bytes.fromhex(outro["pub"])
        qx, _, _ = schnorr.agrega([pub, pub_b])
        de = curva.endereco(qx)
        pend = carrega_pendentes()
        gasto = sum(t["valor"] + t["taxa"] for t in pend if remetente(t) == de)
        if saldos(cadeia).get(de, 0) - gasto < valor + taxa:
            print("a conta conjunta tem %d TEMP livres e isso custa %d."
                  % (saldos(cadeia).get(de, 0) - gasto, valor + taxa)); return
        seq = (sequencias(cadeia).get(de, 0)
               + sum(1 for t in pend if remetente(t) == de))
        tx = {"de": qx.hex(), "para": para, "valor": valor, "taxa": taxa,
              "seq": seq, "quando": int(time.time())}
        qx2, sig = schnorr.assina_junto([priv, priv_b], corpo_tx(tx))
        assert qx2 == qx
        tx["assinatura"] = sig.hex()
        if not tx_valida(tx):
            print("a assinatura conjunta nao conferiu. nada foi enfileirado.")
            return
        pend.append(tx)
        grava_pendentes(pend)
        print("transacao %d da conta conjunta, assinada pelos dois." % seq)
        print("de:   ", de)
        print("para: ", para)
        print("valor: %d %s + %d de taxa" % (valor, SIMBOLO, taxa))
        print("\nassinatura:", sig.hex())
        print("\n64 bytes. Uma. A cadeia vai conferi-la contra uma chave de")
        print("32 bytes e aceitar, sem nunca saber que houve dois donos.")

    elif cmd == "pendentes":
        pend = carrega_pendentes()
        if not pend:
            print("fila vazia"); return
        for tx in pend:
            print("#%-3d %s -> %s  %d %s  taxa %d"
                  % (tx["seq"], remetente(tx)[:12], tx["para"][:12],
                     tx["valor"], SIMBOLO, tx["taxa"]))

    elif cmd == "minerar":
        i = len(cadeia)
        pend = carrega_pendentes()
        s, q = saldos(cadeia), sequencias(cadeia)
        aceitas, mortas, adiadas = [], [], []
        for tx in sorted(pend, key=lambda t: t.get("seq", 0)):
            de = remetente(tx)
            if not tx_valida(tx) or tx["seq"] < q.get(de, 0):
                mortas.append(tx)       # repeticao ou lixo: nao melhora nunca
                continue
            custo = tx["valor"] + tx["taxa"]
            if tx["seq"] != q.get(de, 0) or s.get(de, 0) < custo:
                adiadas.append(tx)      # pode valer num bloco futuro
                continue
            q[de] = q.get(de, 0) + 1
            s[de] -= custo
            s[tx["para"]] = s.get(tx["para"], 0) + tx["valor"]
            aceitas.append(tx)
        taxas = sum(t["taxa"] for t in aceitas)
        premio = recompensa_em(i) + taxas
        txs = list(aceitas)
        if premio > 0:
            txs.insert(0, {"de": None, "para": eu, "valor": premio, "taxa": 0,
                           "seq": None, "quando": int(time.time()),
                           "assinatura": None})
        dif = dificuldade_em(cadeia, i)
        t0 = time.time()
        b = minera_bloco(i, cadeia[-1]["hash"], txs, dif,
                         piso=tempo_mediano(cadeia, i))
        cadeia.append(b)
        grava_cadeia(cadeia)
        grava_pendentes(adiadas)
        print("bloco %d minerado em %.1fs | dificuldade %d zeros"
              % (b["indice"], time.time() - t0, dif))
        print("hash:", b["hash"])
        print("raiz:", b["raiz"])
        print("premio: %d (%d de emissao + %d de taxas)"
              % (premio, recompensa_em(i), taxas))
        print("transacoes: %d aceitas | saldo agora: %d %s"
              % (len(aceitas), saldos(cadeia).get(eu, 0), SIMBOLO))
        if mortas:
            print("%d descartada(s): sequencia ja gasta ou assinatura "
                  "invalida — nao valeriam em bloco nenhum" % len(mortas))
        if adiadas:
            print("%d adiada(s): ficaram na fila esperando a vez ou saldo"
                  % len(adiadas))

    elif cmd == "cadeia":
        print("rede %s (%s) - genese %s"
              % (NOME, SIMBOLO, cadeia[0]["anterior"][:16]))
        for b in cadeia:
            print("#%-3d %s dif:%d txs:%-3d nonce:%-8d raiz:%s"
                  % (b["indice"], b["hash"][:18] + "...",
                     dificuldade_em(cadeia, b["indice"]),
                     len(b["transacoes"]), b["nonce"], b["raiz"][:10] + "..."))

    elif cmd == "emissao":
        criado = sum(tx["valor"] for b in cadeia for tx in b["transacoes"]
                     if tx["de"] is None)
        t = teto()
        print("teto da rede:     %d %s" % (t, SIMBOLO))
        print("ja em circulacao: %d %s (%.2f%%)" % (criado, SIMBOLO, 100.0 * criado / t))
        print("recompensa agora: %d por bloco" % recompensa_em(len(cadeia)))
        print("\nhalving a cada %d blocos:" % HALVING)
        i = 0
        while recompensa_em(i) > 0:
            print("  blocos %4d a %4d -> %d por bloco"
                  % (i, i + HALVING - 1, recompensa_em(i)))
            i += HALVING

    elif cmd == "validar":
        ok, motivo = valida(cadeia)
        print(("OK: " if ok else "INVALIDA: ") + motivo)

    elif cmd == "prova":
        i, n = int(sys.argv[2]), int(sys.argv[3])
        if not (0 <= i < len(cadeia)):
            print("bloco fora da cadeia"); return
        txs = cadeia[i]["transacoes"]
        if not (0 <= n < len(txs)):
            print("o bloco %d tem %d transacoes" % (i, len(txs))); return
        ident = id_tx(txs[n])
        caminho = prova_merkle(txs, n)
        raiz = cadeia[i]["raiz"]
        print("bloco %d, transacao %d de %d" % (i, n, len(txs)))
        print("id da transacao:", ident)
        print("\ncaminho ate a raiz (%d hash%s):"
              % (len(caminho), "es" if len(caminho) != 1 else ""))
        atual = ident
        for passo in caminho:
            nota = "   <- irmao duplicado (o nivel tinha numero impar)" \
                   if passo["hash"] == atual else ""
            print("  junta pela %-9s %s%s" % (passo["lado"], passo["hash"], nota))
            atual = hashlib.sha256(
                ((atual + passo["hash"]) if passo["lado"] == "direita"
                 else (passo["hash"] + atual)).encode()).hexdigest()
        print("\nraiz refeita:  ", end="")
        h = ident
        for passo in caminho:
            junto = ((h + passo["hash"]) if passo["lado"] == "direita"
                     else (passo["hash"] + h))
            h = hashlib.sha256(junto.encode()).hexdigest()
        print(h)
        print("raiz no bloco: ", raiz)
        print("\n" + ("PROVADO" if confere_prova(ident, caminho, raiz)
                      else "NAO BATE"), end=": ")
        if not caminho:
            print("esse bloco tem uma transacao so, entao a raiz E o id dela."
                  "\nnum bloco cheio o caminho cresce com log2 do numero de "
                  "transacoes:\n16 transacoes pedem 4 hashes, 1024 pedem 10.")
        else:
            print("essa transacao esta nesse bloco, e para saber isso bastaram"
                  "\n%d hashes e o cabecalho — nenhuma das outras transacoes."
                  % len(caminho))

    elif cmd == "atrasar":
        # ataque 3: minerar de verdade, com prova de trabalho legitima, mas
        # datando o bloco no passado para a janela de dificuldade parecer
        # longa e a dificuldade cair. nada e gravado: o ataque e montado na
        # memoria e submetido a validacao, como um no faria ao receber.
        if len(cadeia) < 4:
            print("minere uns blocos primeiro"); return
        i = len(cadeia) - 1
        b = cadeia[i]
        piso = tempo_mediano(cadeia, i)
        falso = piso - 60
        dif = dificuldade_em(cadeia, i)
        mentiroso = {"indice": i, "anterior": b["anterior"], "quando": falso,
                     "raiz": b["raiz"], "transacoes": b["transacoes"],
                     "nonce": 0}
        alvo = "0" * dif
        t0 = time.time()
        while True:
            h = hash_bloco(mentiroso)
            if h.startswith(alvo):
                mentiroso["hash"] = h
                break
            mentiroso["nonce"] += 1
        print("reminerei o bloco %d com a data 60s antes da mediana." % i)
        print("gastei %.1fs de prova de trabalho real: %d zeros, nonce %d."
              % (time.time() - t0, dif, mentiroso["nonce"]))
        print("o hash fecha, o bloco aponta para o anterior, as transacoes")
        print("sao as mesmas e a raiz de Merkle bate. so a hora e mentira.")
        falsa = cadeia[:i] + [mentiroso]
        ok, motivo = valida(falsa)
        print("\nveredito de um no que recebesse isso:")
        print(("  ACEITO: " if ok else "  RECUSADO: ") + motivo)
        print("\nnada foi gravado — a sua cadeia continua inteira.")

    elif cmd == "adulterar":
        i = int(sys.argv[2])
        if not (0 < i < len(cadeia)):
            print("indice fora da cadeia"); return
        for tx in cadeia[i]["transacoes"]:
            tx["valor"] = 999999
        grava_cadeia(cadeia)
        print("bloco %d adulterado. rode 'validar'." % i)

    elif cmd == "repetir":
        # pega a ultima transacao assinada da cadeia e devolve ela para a fila
        antiga = None
        for b in reversed(cadeia):
            for tx in b["transacoes"]:
                if tx["de"] is not None:
                    antiga = tx
                    break
            if antiga:
                break
        if antiga is None:
            print("nao ha transacao assinada na cadeia ainda.")
            print("faca uma: enviar <endereco> 10, depois minerar.")
            return
        pend = carrega_pendentes()
        pend.append(dict(antiga))
        grava_pendentes(pend)
        print("peguei uma transacao que JA foi confirmada e devolvi para a fila:")
        print("  %s -> %s  %d %s  sequencia %d"
              % (remetente(antiga)[:12], antiga["para"][:12], antiga["valor"],
                 SIMBOLO, antiga["seq"]))
        print("\na assinatura dela e autentica, nao foi tocada. e exatamente o")
        print("que um atacante teria: uma ordem de pagamento valida, assinada")
        print("pela vitima, pronta para ser cobrada de novo.")
        print("\nrode 'minerar' e veja o que acontece com ela.")

    else:
        print(__doc__)


if __name__ == "__main__":
    main()
