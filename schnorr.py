# -*- coding: utf-8 -*-
"""Schnorr na secp256k1, e a soma de chaves que o ECDSA nao sabe fazer.

Claus Schnorr publicou isto em 1989 e patenteou. A patente so caiu em
2008, e o Bitcoin nasceu em 2009 com ECDSA — que e mais complicado, mais
feio de provar seguro, e foi escolhido por estar livre. O Bitcoin levou
ate 2021 para ganhar Schnorr, no Taproot.

A assinatura inteira e isto:

    s = k + e*d        assinar
    s*G == R + e*P     conferir

Uma linha de algebra em cada lado. O ECDSA precisa de inversao modular e
de uma regra extra contra maleabilidade; aqui a propria equacao e linear,
e a linearidade e o que da o presente de graca:

    SOMA DE CHAVES. Duas chaves publicas somam numa terceira, e os dois
    donos assinam junto produzindo UMA assinatura. Quem confere nao
    consegue distinguir de uma pessoa so. Nao ha campo novo no bloco,
    nao ha multisig declarada, nao ha como a rede saber que sao dois.

Isso e o que o ECDSA nao permite: a inversao de `k` quebra a soma.

Aqui dentro esta a BIP-340, a especificacao do Bitcoin, nao uma versao
caseira. A diferenca aparece em tres detalhes que parecem frescura e nao
sao: chave publica de 32 bytes com o y PAR implicito, hash etiquetado
para que um hash de nonce nunca possa ser lido como hash de desafio, e
nonce derivado da chave em vez de sorteado — porque sortear duas vezes o
mesmo `k` revela a chave privada, e foi assim que a Sony perdeu a do
PlayStation 3 em 2010.

    python3 schnorr.py vetores     confere contra os vetores oficiais
    python3 schnorr.py dois        dois donos, uma assinatura
    python3 schnorr.py ataque      por que a soma ingenua e roubavel
"""
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import curva

P, N, G = curva.P, curva.N, curva.G


# ----------------------------------------------------------- fundamentos

def _etiqueta(tag, *partes):
    """sha256(sha256(tag) || sha256(tag) || m), a hash etiquetada da BIP-340.

    O prefixo duplo faz com que dois usos diferentes do sha256 nunca
    possam colidir de proposito: um hash feito para nonce nao e aceito
    como hash de desafio nem se o atacante escolher a mensagem.
    """
    t = hashlib.sha256(tag.encode()).digest()
    return hashlib.sha256(t + t + b"".join(partes)).digest()


def _par(ponto):
    return ponto[1] % 2 == 0


def _ergue(x_bytes):
    """Do x de 32 bytes ao ponto da curva com y PAR. None se nao existir.

    Como p = 3 (mod 4), a raiz quadrada e a^((p+1)/4). Dos dois y
    possiveis a BIP-340 escolhe sempre o par, e e por isso que a chave
    publica cabe em 32 bytes em vez de 64.
    """
    x = int.from_bytes(x_bytes, "big")
    if x >= P:
        return None
    y2 = (pow(x, 3, P) + 7) % P
    y = pow(y2, (P + 1) // 4, P)
    if pow(y, 2, P) != y2:
        return None                      # x nao esta na curva
    return (x, y if y % 2 == 0 else P - y)


def publica(priv):
    """32 bytes: so a coordenada x. O y par fica implicito."""
    return curva.multiplica(priv, G)[0].to_bytes(32, "big")


# ------------------------------------------------- assinar e conferir (1)

def assina(priv, msg, aux=None):
    if not 1 <= priv < N:
        raise ValueError("chave privada fora do intervalo")
    Pp = curva.multiplica(priv, G)
    d = priv if _par(Pp) else N - priv
    px = Pp[0].to_bytes(32, "big")
    if aux is None:
        aux = os.urandom(32)
    # o nonce sai da chave e da mensagem, nao de um sorteio: duas
    # assinaturas diferentes jamais reusam o mesmo k por acidente
    t = (d ^ int.from_bytes(_etiqueta("BIP0340/aux", aux), "big"))
    k0 = int.from_bytes(
        _etiqueta("BIP0340/nonce", t.to_bytes(32, "big"), px, msg), "big") % N
    if k0 == 0:
        raise ValueError("nonce zero")
    R = curva.multiplica(k0, G)
    k = k0 if _par(R) else N - k0
    rx = R[0].to_bytes(32, "big")
    e = int.from_bytes(_etiqueta("BIP0340/challenge", rx, px, msg), "big") % N
    return rx + ((k + e * d) % N).to_bytes(32, "big")


def confere(pubx, msg, assinatura):
    try:
        if len(assinatura) != 64 or len(pubx) != 32:
            return False
        Pp = _ergue(pubx)
        if Pp is None:
            return False
        r = int.from_bytes(assinatura[:32], "big")
        s = int.from_bytes(assinatura[32:], "big")
        if r >= P or s >= N:
            return False
        e = int.from_bytes(
            _etiqueta("BIP0340/challenge", assinatura[:32], pubx, msg),
            "big") % N
        # R = s*G - e*P
        R = curva.soma(curva.multiplica(s, G), curva.multiplica(N - e, Pp))
        return R is not None and _par(R) and R[0] == r
    except Exception:
        return False


# -------------------------------------------------------- soma de chaves

def coeficientes(pubs):
    """Um peso por chave, derivado da LISTA INTEIRA de chaves.

    Sem esse peso, somar chaves e roubavel: o ultimo a escolher a sua
    pode escolhe-la de modo a ser dono da soma sozinho. Com ele, mudar a
    propria chave muda o proprio peso, e a conta nao fecha mais para o
    atacante. Rode `python3 schnorr.py ataque` para ver os dois casos.
    """
    lista = sorted(pubs)
    L = _etiqueta("Tempest/agg/lista", b"".join(lista))
    return {p: int.from_bytes(_etiqueta("Tempest/agg/coef", L, p), "big") % N
            for p in lista}


def agrega(pubs):
    """A chave publica conjunta. Devolve (32 bytes x, ponto, coeficientes)."""
    a = coeficientes(pubs)
    Q = None
    for p in sorted(pubs):
        Q = curva.soma(Q, curva.multiplica(a[p], _ergue(p)))
    if Q is None:
        raise ValueError("soma deu o ponto no infinito")
    return Q[0].to_bytes(32, "big"), Q, a


def assina_junto(privs, msg):
    """Assinatura conjunta de varios donos. Devolve (pubx_conjunta, sig).

    Aqui esta tudo num processo so, por ser demonstracao. Numa rede de
    verdade cada rodada abaixo e uma mensagem entre maquinas, e a ordem
    importa: os nonces TEM que ser trocados antes de qualquer assinatura
    parcial, senao quem fala por ultimo escolhe o proprio nonce depois de
    ver o dos outros e forja a assinatura do grupo.
    """
    pubs = [publica(d) for d in privs]
    qx, Q, a = agrega(pubs)
    g = 1 if _par(Q) else N - 1          # corrige a paridade do conjunto

    # rodada 1: cada um sorteia o seu nonce e publica R_i
    ks, Rs = [], []
    for _ in privs:
        k = curva.chave_privada()
        ks.append(k)
        Rs.append(curva.multiplica(k, G))
    R = None
    for ri in Rs:
        R = curva.soma(R, ri)
    gr = 1 if _par(R) else N - 1         # idem para o nonce somado
    rx = R[0].to_bytes(32, "big")
    e = int.from_bytes(_etiqueta("BIP0340/challenge", rx, qx, msg), "big") % N

    # rodada 2: cada um devolve a sua parte da assinatura
    s = 0
    for d_bruto, k, p in zip(privs, ks, pubs):
        Pi = curva.multiplica(d_bruto, G)
        d = d_bruto if _par(Pi) else N - d_bruto
        s = (s + k * gr + e * a[p] * g * d) % N
    return qx, rx + s.to_bytes(32, "big")


# -------------------------------------------------------------------- cli

def _vetores():
    import csv
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "bip340.csv")
    if not os.path.exists(caminho):
        print("falta o arquivo bip340.csv nesta pasta.")
        print("baixe com:")
        print("  curl -sS -o bip340.csv https://raw.githubusercontent.com"
              "/bitcoin/bips/master/bip-0340/test-vectors.csv")
        return
    ok = ruim = 0
    for v in csv.DictReader(open(caminho)):
        pub = bytes.fromhex(v["public key"])
        msg = bytes.fromhex(v["message"])
        sig = bytes.fromhex(v["signature"])
        esperado = v["verification result"] == "TRUE"
        obtido = confere(pub, msg, sig)
        marca = "ok " if obtido == esperado else "ERRO"
        if obtido == esperado:
            ok += 1
        else:
            ruim += 1
        # onde ha chave privada, confere tambem que ASSINAR reproduz a
        # assinatura oficial byte a byte
        extra = ""
        if v["secret key"]:
            meu = assina(int(v["secret key"], 16), msg,
                         bytes.fromhex(v["aux_rand"]))
            if meu == sig:
                extra = " | assinatura identica a oficial"
            else:
                extra = " | ASSINATURA DIFERENTE"
                ruim += 1
        print("%s vetor %-2s %s%s" % (marca, v["index"],
              (v["comment"] or "caso valido")[:46], extra))
    print("\n%d conferem, %d divergem" % (ok, ruim))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "ajuda"

    if cmd == "vetores":
        _vetores()

    elif cmd == "dois":
        da, db = curva.chave_privada(), curva.chave_privada()
        pa, pb = publica(da), publica(db)
        msg = hashlib.sha256(b"paga 100 TEMP para a obra").digest()
        qx, _, _ = agrega([pa, pb])
        print("chave de Ana:   ", pa.hex())
        print("chave de Bento: ", pb.hex())
        print("chave conjunta: ", qx.hex())
        print("\nA conjunta nao e nenhuma das duas, e nem Ana nem Bento")
        print("conhece a chave privada dela — ela nao existe em lugar nenhum.")
        qx2, sig = assina_junto([da, db], msg)
        print("\nassinatura conjunta:", sig.hex())
        print("confere contra a chave conjunta:", confere(qx2, msg, sig))
        print("\nAgora o que importa: Ana sozinha consegue?")
        sa = assina(da, msg)
        print("  assinatura so de Ana contra a conjunta:",
              confere(qx, msg, sa))
        print("  endereco Tempest da conjunta:",
              curva.endereco(qx))
        print("\nE do lado de quem confere, nada disso aparece: sao 64 bytes")
        print("de assinatura e 32 de chave, exatamente como seriam de uma")
        print("pessoa so. A rede nao sabe que sao dois, nem quantos sao.")

    elif cmd == "ataque":
        print("O ATAQUE DA CHAVE FORJADA, contra a soma ingenua Q = Pa + Pb.\n")
        da = curva.chave_privada()
        Pa = curva.multiplica(da, G)
        print("Ana publica a chave dela. Bento ve a chave de Ana ANTES de")
        print("escolher a sua — e esse e o unico ingrediente do ataque.\n")
        # Bento escolhe x e publica Pb = x*G - Pa. A soma vira x*G.
        x = curva.chave_privada()
        Pb = curva.soma(curva.multiplica(x, G), curva.multiplica(N - 1, Pa))
        Q_ingenuo = curva.soma(Pa, Pb)
        print("Bento escolhe um x secreto e publica Pb = x*G - Pa.")
        print("A soma ingenua fica Pa + (x*G - Pa) = x*G:")
        print("  Q da soma ingenua  :", Q_ingenuo[0].to_bytes(32, "big").hex())
        print("  x*G, que so Bento sabe:",
              curva.multiplica(x, G)[0].to_bytes(32, "big").hex())
        print("  sao o mesmo ponto:", Q_ingenuo == curva.multiplica(x, G))
        msg = hashlib.sha256(b"esvazia a conta conjunta").digest()
        # Bento assina sozinho, como dono unico de Q
        d = x if _par(Q_ingenuo) else N - x
        sig = assina(d, msg)
        print("\nBento assina SOZINHO e a assinatura confere contra a conta")
        print("conjunta:", confere(Q_ingenuo[0].to_bytes(32, "big"), msg, sig))
        print("Ana nunca participou. O dinheiro dos dois e dele.\n")
        print("-" * 58)
        print("\nAgora a mesma tentativa, com os coeficientes da MuSig.\n")
        pa, pb = Pa[0].to_bytes(32, "big"), Pb[0].to_bytes(32, "big")
        qx, Q, a = agrega([pa, pb])
        print("Q = a_Ana*Pa + a_Bento*Pb, e cada peso sai do hash da lista")
        print("inteira de chaves. Entao a chave de Bento entra na conta que")
        print("define o peso dela propria.")
        print("  Q com coeficientes:", qx.hex())
        print("  Bento assinando sozinho confere:", confere(qx, msg, sig))
        d2 = x if _par(Q) else N - x
        print("  e tentando de novo com a paridade certa:",
              confere(qx, msg, assina(d2, msg)))
        print("\nPara repetir o golpe, Bento precisaria escolher Pb sabendo o")
        print("hash de uma lista que contem Pb. E um ponto fixo de uma funcao")
        print("de hash, que e exatamente o que ninguem sabe achar.")
        print("\nE a assinatura conjunta legitima, essa continua funcionando:")
        qx3, sig3 = assina_junto([da, x], msg)
        print("  dois donos assinando junto:", confere(qx3, msg, sig3))

    else:
        print(__doc__)


if __name__ == "__main__":
    main()
