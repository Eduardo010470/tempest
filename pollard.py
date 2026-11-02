# -*- coding: utf-8 -*-
"""Pollard rho: quanto custa quebrar uma chave, medido em vez de afirmado.

A chave privada e um numero k. A publica e o ponto Q = k*G. Quebrar a
chave e achar k tendo Q, o problema do logaritmo discreto.

Forca bruta custa n tentativas, onde n e a ordem do grupo. O rho custa
RAIZ de n. Essa raiz e a resposta para uma pergunta que quase ninguem
faz: por que 256 bits, e nao 128? Porque o melhor ataque conhecido
precisa de 2^128 passos contra uma chave de 256 bits. A secp256k1 tem
chave de 256 bits e seguranca de 128. Metade do numero nao e desperdicio,
e o preco do rho.

Aqui o rho roda de verdade. A mesma equacao da secp256k1, y^2 = x^3 + 7,
sobre corpos pequenos onde da para esperar o fim. As chaves quebram na
sua frente, os passos sao contados, e a constante 1.2533 aparece sozinha
nos numeros. O ultimo comando mede a velocidade DESTA maquina e faz a
conta para 256 bits.

    python3 pollard.py curvas          # as curvas pequenas, conferidas
    python3 pollard.py rho [bits]      # quebra uma chave e conta os passos
    python3 pollard.py lei             # passos / raiz(n): a constante
    python3 pollard.py canguru [bits]  # na secp256k1 de verdade
    python3 pollard.py conta           # a extrapolacao para 256 bits
"""
import math
import random
import sys
import time

import curva

# As curvas pequenas: (p, Gx, Gy, n), todas com y^2 = x^3 + 7, p = 3 mod 4,
# e n = #E(F_p) PRIMO. Nada aqui e para confiar: `curvas` confere tudo.
PEQUENAS = [
    (65419, 3, 48428, 64921),
    (1046047, 1, 194336, 1046779),
    (16776547, 2, 15459074, 16769119),
    (268431571, 3, 72237204, 268410001),
    (4294965679, 1, 1017994541, 4294850827),
    (68719475707, 2, 39864926934, 68718961147),
    (1099511622367, 1, 999228730009, 1099513423039),
]


# ------------------------------------------------------------------ curva
# As mesmas formulas do curva.py, com o corpo como parametro. E de
# proposito: o rho so depende da ORDEM do grupo, nao do tamanho do primo,
# e rodar a identica equacao sobre um corpo pequeno e o que torna isso
# verificavel numa tarde em vez de numa eternidade.

def soma(p, A, B):
    if A is None:
        return B
    if B is None:
        return A
    x1, y1 = A
    x2, y2 = B
    if x1 == x2 and (y1 + y2) % p == 0:
        return None
    if A == B:
        lam = 3 * x1 * x1 * pow(2 * y1, p - 2, p) % p
    else:
        lam = (y2 - y1) * pow(x2 - x1, p - 2, p) % p
    x3 = (lam * lam - x1 - x2) % p
    return (x3, (lam * (x1 - x3) - y1) % p)


def mult(p, k, A):
    if A is None or k == 0:
        return None
    if k < 0:
        k, A = -k, (A[0], (-A[1]) % p)
    R = None
    while k:
        if k & 1:
            R = soma(p, R, A)
        A = soma(p, A, A)
        k >>= 1
    return R


def na_curva(p, A):
    return A is None or (A[1] * A[1] - A[0] ** 3 - 7) % p == 0


def primo(n):
    """Miller-Rabin. Para numeros deste tamanho as bases fixas bastam."""
    if n < 2:
        return False
    for q in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % q == 0:
            return n == q
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for a in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def escolhe(bits):
    """A curva pequena mais proxima do tamanho pedido."""
    return min(PEQUENAS, key=lambda c: abs(c[3].bit_length() - bits))


# -------------------------------------------------------------- Pollard rho

def rho(p, G, Q, n, semente=None, saltos=32):
    """Acha k com Q = k*G, num grupo de ordem prima n. Devolve (k, passos).

    O passeio guarda sempre um par (a, b) com X = a*G + b*Q, e anda somando
    um dos 32 saltos pre-sorteados, escolhido pelo proprio X. Quando dois
    pontos do passeio coincidem, duas combinacoes diferentes de (a, b) dao
    o MESMO ponto:

        a1*G + b1*Q = a2*G + b2*Q   com Q = k*G
        a1 + b1*k   = a2 + b2*k     (mod n)
        k = (a1 - a2) / (b2 - b1)   (mod n)

    E uma colisao de aniversario: num grupo de n elementos, bastam cerca
    de raiz(pi*n/2) pontos para dois coincidirem. Nao ha busca, nao ha
    palpite sobre k. So o fato de o passeio nao ter para onde fugir.

    O passeio nao guarda todos os pontos — guarda so os DISTINGUIDOS, os
    que terminam em w bits zero. Com isso a memoria cai para cerca de mil
    entradas e o tempo nao muda: a colisao acontece do mesmo jeito, so e
    notada alguns passos depois.
    """
    rnd = random.Random(semente)
    us = [rnd.randrange(1, n) for _ in range(saltos)]
    vs = [rnd.randrange(1, n) for _ in range(saltos)]
    pulos = [soma(p, mult(p, us[j], G), mult(p, vs[j], Q))
             for j in range(saltos)]

    w = max(0, math.isqrt(n).bit_length() - 10)
    masc = (1 << w) - 1

    def largada():
        a, b = rnd.randrange(1, n), rnd.randrange(1, n)
        return a, b, soma(p, mult(p, a, G), mult(p, b, Q))

    a, b, X = largada()
    vistos = {}
    passos = 0
    while True:
        if X is None:                      # a*G + b*Q = infinito
            if b % n:
                return (-a * pow(b, -1, n)) % n, passos
            a, b, X = largada()
            continue
        if not (X[0] & masc):
            if X in vistos:
                a2, b2 = vistos[X]
                db = (b2 - b) % n
                if db:
                    return (a - a2) * pow(db, -1, n) % n, passos
                a, b, X = largada()        # colisao sem informacao
                continue
            vistos[X] = (a, b)
        j = X[0] % saltos
        a = (a + us[j]) % n
        b = (b + vs[j]) % n
        X = soma(p, X, pulos[j])
        passos += 1


# ---------------------------------------------------- Pollard canguru (lambda)

def canguru(Q, bits, teto=40):
    """Acha k com Q = k*G na secp256k1, sabendo que k esta em [0, 2^bits).

    O rho precisa de raiz da ORDEM do grupo, e a ordem da secp256k1 tem
    256 bits — raiz disso ainda e 2^128. Mas quando se sabe que a chave
    cai num INTERVALO, o custo passa a ser a raiz do intervalo. E essa e a
    situacao real de quase todo vazamento: carteira feita com relogio como
    semente, com dado de seis lados, com frase escolhida a mao.

    Dois cangurus pulam para a frente com passos de tamanho conhecido. O
    manso parte de um ponto que se sabe qual e; o selvagem parte de Q, que
    e um ponto cuja posicao ninguem sabe. Como o tamanho de cada pulo
    depende so de onde o canguru esta, se o selvagem cair numa pegada do
    manso ele passa a seguir exatamente o mesmo caminho — e a distancia
    percorrida por cada um revela a diferenca entre as largadas.
    """
    W = 1 << bits
    raiz = math.isqrt(W)

    # O tamanho medio do pulo e o unico parametro que importa: raiz(W)/2.
    # Pulo pequeno demais e um canguru que nao sai do lugar; grande demais
    # e um que salta por cima da pegada do outro sem pisar nela.
    alvo = max(1, raiz // 2)
    J = 2
    while J < bits + 8 and ((1 << (J + 1)) - 1) / (J + 1) <= alvo:
        J += 1
    pulos = [1 << i for i in range(J)]
    pontos = [curva.multiplica(s, curva.G) for s in pulos]

    w = max(0, raiz.bit_length() - 8)
    masc = (1 << w) - 1
    orcamento = teto * raiz

    rnd = random.SystemRandom()
    dt = W // 2
    T = curva.multiplica(dt, curva.G)
    dw = 0
    S = Q
    pegadas = {}
    passos = 0

    while passos < orcamento:
        for tipo in (0, 1):
            X, d = (T, dt) if tipo == 0 else (S, dw)
            if X is None:
                break
            if not (X[0] & masc):
                achado = pegadas.get(X)
                if achado is not None:
                    t2, d2 = achado
                    if t2 != tipo:
                        # posicao do manso = dt; a do selvagem = k + dw.
                        # pisaram no mesmo ponto, logo dt = k + dw.
                        k = (d - d2) if tipo == 0 else (d2 - d)
                        return k % curva.N, passos
                    # dois cangurus do mesmo tipo: um deles entrou em
                    # circulo. recomeca esse com outra largada.
                    if tipo == 0:
                        dt = rnd.randrange(W)
                        T = curva.multiplica(dt, curva.G)
                    else:
                        dw = rnd.randrange(W)
                        S = curva.soma(Q, curva.multiplica(dw, curva.G))
                    continue
                pegadas[X] = (tipo, d)
            j = X[0] % J
            if tipo == 0:
                dt += pulos[j]
                T = curva.soma(T, pontos[j])
            else:
                dw += pulos[j]
                S = curva.soma(S, pontos[j])
            passos += 1
    return None, passos


# ------------------------------------------------------------------ comandos

def cmd_curvas():
    print("As curvas pequenas. Mesma equacao da secp256k1, y^2 = x^3 + 7,")
    print("so o corpo e menor. Cada linha e conferida agora:\n")
    print("  bits    p                 n (ordem)        raiz(n)")
    for p, gx, gy, n in PEQUENAS:
        G = (gx, gy)
        assert primo(p), "p nao e primo"
        assert p % 4 == 3, "p nao e 3 mod 4"
        assert na_curva(p, G), "G fora da curva"
        assert primo(n), "a ordem nao e prima"
        assert mult(p, n, G) is None, "n*G nao e o infinito"
        r = math.isqrt(p)
        assert p + 1 - 2 * r <= n <= p + 1 + 2 * r, "fora do intervalo de Hasse"
        print("  %4d  %16d  %16d  %10d"
              % (n.bit_length(), p, n, math.isqrt(n)))
    print("\nTudo conferido: p primo, p = 3 mod 4, G na curva, n primo,")
    print("n*G = infinito, e n dentro do intervalo de Hasse (o teorema que")
    print("obriga a ordem a ficar a menos de 2*raiz(p) de p+1).")
    print("\nA secp256k1, para comparar:")
    print("  %4d  %s" % (curva.N.bit_length(), hex(curva.N)))
    print("  raiz(n) = 2^128 = %d" % math.isqrt(curva.N))


def cmd_rho(bits):
    p, gx, gy, n = escolhe(bits)
    G = (gx, gy)
    k = random.SystemRandom().randrange(1, n)
    Q = mult(p, k, G)
    print("curva: y^2 = x^3 + 7 sobre F_%d" % p)
    print("ordem do grupo: %d (%d bits)" % (n, n.bit_length()))
    print()
    print("chave privada sorteada: %d" % k)
    print("chave publica Q = k*G:  (%d, %d)" % Q)
    print()
    print("agora esquece o k e acha ele so com o Q.")
    print("forca bruta custaria %d passos. o rho:" % n)
    print()
    t0 = time.time()
    achado, passos = rho(p, G, Q, n)
    dt = time.time() - t0
    assert mult(p, achado, G) == Q, "o rho devolveu um k que nao fecha"
    print("k = %d   %s" % (achado, "CERTO" if achado == k else "ERRADO"))
    print("passos: %d em %.2f s (%.0f por segundo)"
          % (passos, dt, passos / dt if dt else 0))
    print()
    r = math.isqrt(n)
    print("raiz(n) = %d, e o rho gastou %.2f disso." % (r, passos / r))
    print("forca bruta teria gasto %.0f vezes mais." % (n / passos))


def cmd_lei():
    print("A lei da raiz, medida. Para cada ordem n, o rho e repetido e")
    print("os passos sao divididos por raiz(n). O valor que deve aparecer")
    print("e raiz(pi/2) = %.4f, a constante da colisao de aniversario.\n"
          % math.sqrt(math.pi / 2))
    print("  bits        n      raiz(n)   repet.   passos (media)   /raiz(n)")
    rnd = random.SystemRandom()
    for p, gx, gy, n in PEQUENAS[:4]:
        G = (gx, gy)
        # orcamento parecido por linha: as ordens pequenas repetem mais,
        # senao a media de poucas amostras balanca mais que a propria lei
        reps = max(10, min(60, 400000 // int(1.25 * math.isqrt(n))))
        total = 0
        for _ in range(reps):
            k = rnd.randrange(1, n)
            achado, passos = rho(p, G, mult(p, k, G), n)
            assert achado == k
            total += passos
        media = total / reps
        print("  %4d %12d %10d %8d %14.0f %10.4f"
              % (n.bit_length(), n, math.isqrt(n), reps, media,
                 media / math.isqrt(n)))
    print("\nO expoente e o que importa: cada 2 bits a mais na chave custam")
    print("1 bit a mais de ataque. Dobrar o tamanho da chave eleva o custo")
    print("do ataque ao quadrado, e e por isso que 256 bits bastam para")
    print("sempre enquanto 128 bastariam so para hoje.")


def cmd_canguru(bits):
    print("Agora na secp256k1 DE VERDADE — a curva do Bitcoin, os mesmos")
    print("256 bits, o mesmo G. O que muda e a chave: ela foi sorteada")
    print("dentro de um intervalo de %d bits, como uma carteira feita com" % bits)
    print("entropia ruim.\n")
    k = random.SystemRandom().randrange(1, 1 << bits)
    Q = curva.multiplica(k, curva.G)
    print("chave privada: %d" % k)
    print("chave publica: %s" % curva.chave_publica(k)[:32].hex())
    print("              (x de 32 bytes, igualzinha a uma chave boa)\n")
    print("intervalo: 2^%d = %d chaves possiveis" % (bits, 1 << bits))
    print("raiz dele: %d. o canguru precisa de umas duas vezes isso."
          % math.isqrt(1 << bits))
    print()
    t0 = time.time()
    achado, passos = canguru(Q, bits)
    dt = time.time() - t0
    if achado is None:
        print("o orcamento acabou em %d passos (%.1f s)." % (passos, dt))
        print("o canguru e probabilistico: rode de novo.")
        return
    assert curva.multiplica(achado, curva.G) == Q
    print("k = %d   %s" % (achado, "CERTO" if achado == k else "ERRADO"))
    print("passos: %d em %.1f s (%.0f somas de ponto por segundo)"
          % (passos, dt, passos / dt if dt else 0))
    print()
    print("%d chaves possiveis, quebradas em %d passos." % (1 << bits, passos))
    print("Nenhuma delas foi testada. O custo foi a RAIZ do intervalo.")
    print()
    print("E por isso que chave nao se escolhe, se sorteia — com os 256")
    print("bits inteiros. Entropia de %d bits da %d bits de seguranca."
          % (bits, bits // 2))


def cmd_conta():
    print("A conta, com a velocidade medida nesta maquina.\n")
    A = curva.multiplica(7, curva.G)
    B = curva.multiplica(11, curva.G)
    t0 = time.time()
    n = 0
    while time.time() - t0 < 1.5:
        for _ in range(200):
            A = curva.soma(A, B)
        n += 200
    taxa = n / (time.time() - t0)
    print("somas de ponto na secp256k1: %.0f por segundo" % taxa)

    passos = 1.2533 * math.isqrt(curva.N)
    print("passos que o rho precisa:    %.3e  (raiz(pi*n/2))" % passos)
    segundos = passos / taxa
    anos = segundos / 31557600.0
    print("tempo nesta maquina:         %.3e anos" % anos)
    print("idade do universo:           1.380e+10 anos")
    print("                             %.2e vezes a idade do universo"
          % (anos / 1.38e10))
    print()
    print("E se a rede inteira do Bitcoin fosse convertida em somas de")
    print("ponto? Ela faz 888 EH/s, ou 8.88e20 operacoes por segundo:")
    coletivo = passos / 8.88e20 / 31557600.0
    print("  %.3e anos — %.1f vezes a idade do universo, com todo o"
          % (coletivo, coletivo / 1.38e10))
    print("  poder de calculo que a humanidade ja apontou para uma coisa so.")
    print()
    uma_hora = taxa * 3600
    bits_hora = 2 * math.log2(uma_hora / 1.2533)
    print("O que ESTA maquina quebra em uma hora: chave de %.0f bits."
          % bits_hora)
    print("A de 256 bits custa 2^%d vezes mais que essa hora."
          % int((256 - bits_hora) / 2))
    print()
    print("Nada disso depende de a secp256k1 ser bem feita, de o Bitcoin")
    print("ser popular ou de haver dinheiro em jogo. E a raiz quadrada.")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "curvas"
    arg = int(sys.argv[2]) if len(sys.argv) > 2 else None
    if cmd == "curvas":
        cmd_curvas()
    elif cmd == "rho":
        cmd_rho(arg or 32)
    elif cmd == "lei":
        cmd_lei()
    elif cmd == "canguru":
        cmd_canguru(arg or 28)
    elif cmd == "conta":
        cmd_conta()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
