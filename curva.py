# -*- coding: utf-8 -*-
"""secp256k1 em Python puro — a mesma curva do Bitcoin.

Nada de biblioteca externa. Serve para assinar e conferir assinatura,
que e o que impede alguem de gastar moeda que nao e dele.
"""
import hashlib
import os

# Parametros da curva secp256k1, definidos no padrao SEC 2.
P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
G = (0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
     0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8)


def soma(p1, p2):
    """Soma dois pontos da curva. O 'None' representa o ponto no infinito."""
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2 and (y1 + y2) % P == 0:
        return None
    if p1 == p2:
        lam = (3 * x1 * x1) * pow(2 * y1, P - 2, P) % P
    else:
        lam = (y2 - y1) * pow(x2 - x1, P - 2, P) % P
    x3 = (lam * lam - x1 - x2) % P
    y3 = (lam * (x1 - x3) - y1) % P
    return (x3, y3)


def multiplica(k, ponto):
    """Multiplicacao escalar por dobra e soma."""
    r = None
    while k:
        if k & 1:
            r = soma(r, ponto)
        ponto = soma(ponto, ponto)
        k >>= 1
    return r


def chave_privada():
    while True:
        k = int.from_bytes(os.urandom(32), "big")
        if 1 <= k < N:
            return k


def chave_publica(priv):
    x, y = multiplica(priv, G)
    return x.to_bytes(32, "big") + y.to_bytes(32, "big")


def assina(priv, mensagem):
    z = int.from_bytes(hashlib.sha256(mensagem).digest(), "big")
    while True:
        k = chave_privada()
        ponto = multiplica(k, G)
        r = ponto[0] % N
        if r == 0:
            continue
        s = (pow(k, N - 2, N) * (z + r * priv)) % N
        if s == 0:
            continue
        # assinatura canonica: evita a forma maleavel com s alto
        if s > N // 2:
            s = N - s
        return r.to_bytes(32, "big") + s.to_bytes(32, "big")


def confere(pub, mensagem, assinatura):
    try:
        r = int.from_bytes(assinatura[:32], "big")
        s = int.from_bytes(assinatura[32:], "big")
        if not (1 <= r < N and 1 <= s < N):
            return False
        x = int.from_bytes(pub[:32], "big")
        y = int.from_bytes(pub[32:], "big")
        if (y * y - x * x * x - 7) % P != 0:      # o ponto esta na curva?
            return False
        z = int.from_bytes(hashlib.sha256(mensagem).digest(), "big")
        si = pow(s, N - 2, N)
        ponto = soma(multiplica(z * si % N, G), multiplica(r * si % N, (x, y)))
        return ponto is not None and ponto[0] % N == r
    except Exception:
        return False


def endereco(pub):
    """Endereco = primeiros 20 bytes do sha256 da chave publica."""
    return hashlib.sha256(pub).hexdigest()[:40]
