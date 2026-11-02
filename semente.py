# -*- coding: utf-8 -*-
"""Semente de doze palavras — o backup da carteira do Tempest.

O problema que isto resolve: a chave privada e um numero de 256 bits.
Perder o arquivo que a guarda e perder as moedas, para sempre, sem
atendimento, sem recuperacao, sem ninguem para quem reclamar. E um
numero desses nao se copia a mao sem errar um digito.

A solucao que o mundo todo adotou e a BIP-39, de 2013: traduzir o
numero para palavras de uma lista fechada. Doze palavras de uma lista
de 2048 carregam 132 bits — 128 de aleatoriedade mais 4 de soma de
verificacao. Os 4 bits de verificacao sao o detalhe esperto: se voce
copiar uma palavra errada, a frase nao fecha, e o programa avisa em
vez de te entregar uma carteira vazia e silenciosa.

A lista e a oficial da BIP-39 em portugues, a mesma que as carteiras
de verdade usam, extraida do pacote de referencia da Trezor. Duas
propriedades dela merecem nota: nenhuma palavra tem acento, e as
quatro primeiras letras de cada uma ja sao unicas — da para anotar
so quatro letras e ainda assim nao haver duvida.

Da frase para a chave o caminho e o da BIP-39: PBKDF2-HMAC-SHA512,
2048 rodadas, sal "mnemonic". As 2048 rodadas existem para encarecer
quem tentar adivinhar a frase por forca bruta.

Uma honestidade sobre o escopo: as carteiras de verdade seguem daqui
para a BIP-32, que deriva uma arvore infinita de chaves a partir
dessa semente, e e por isso que elas te dao um endereco novo a cada
recebimento. Aqui a semente gera UMA chave. O backup funciona igual;
a privacidade de varios enderecos nao esta implementada.
"""
import hashlib
import hmac
import os
import secrets
import unicodedata

ARQ_PALAVRAS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "palavras.txt")

# a ordem da curva secp256k1: a chave privada tem que ser menor que isso
ORDEM = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141


def palavras():
    with open(ARQ_PALAVRAS, encoding="utf-8") as f:
        lista = f.read().split()
    if len(lista) != 2048:
        raise ValueError("a lista de palavras deveria ter 2048, tem %d"
                         % len(lista))
    return lista


def gera_frase(bits=128):
    """Sorteia entropia de verdade e a escreve em palavras."""
    if bits not in (128, 160, 192, 224, 256):
        raise ValueError("bits invalidos para BIP-39")
    entropia = secrets.token_bytes(bits // 8)
    return frase_de(entropia)


def frase_de(entropia):
    """Converte bytes de entropia na frase, com a soma de verificacao."""
    bits = len(entropia) * 8
    n_soma = bits // 32
    soma = hashlib.sha256(entropia).digest()[0] >> (8 - n_soma)
    inteiro = (int.from_bytes(entropia, "big") << n_soma) | soma
    total = bits + n_soma
    lista = palavras()
    saida = []
    for i in range(total // 11):
        # le os 11 bits de cada grupo, do mais alto para o mais baixo
        desloca = total - 11 * (i + 1)
        saida.append(lista[(inteiro >> desloca) & 0x7FF])
    return " ".join(saida)


def normaliza(frase):
    return unicodedata.normalize("NFKD", " ".join(frase.lower().split()))


def confere_frase(frase):
    """Devolve (ok, motivo). Pega palavra errada e palavra trocada de lugar."""
    partes = normaliza(frase).split()
    if len(partes) not in (12, 15, 18, 21, 24):
        return False, ("a frase tem %d palavras; precisa ter 12, 15, 18, 21 "
                       "ou 24" % len(partes))
    lista = palavras()
    indice = {p: i for i, p in enumerate(lista)}
    for p in partes:
        if p not in indice:
            return False, "a palavra '%s' nao esta na lista da BIP-39" % p
    total = len(partes) * 11
    n_soma = total // 33
    bits = total - n_soma
    inteiro = 0
    for p in partes:
        inteiro = (inteiro << 11) | indice[p]
    soma = inteiro & ((1 << n_soma) - 1)
    entropia = (inteiro >> n_soma).to_bytes(bits // 8, "big")
    esperada = hashlib.sha256(entropia).digest()[0] >> (8 - n_soma)
    if soma != esperada:
        return False, ("a soma de verificacao nao fecha — alguma palavra "
                       "esta errada ou fora de ordem")
    return True, "frase valida"


def semente_de(frase, senha=""):
    """A semente de 64 bytes da BIP-39. 2048 rodadas para encarecer chute."""
    return hashlib.pbkdf2_hmac(
        "sha512", normaliza(frase).encode("utf-8"),
        ("mnemonic" + unicodedata.normalize("NFKD", senha)).encode("utf-8"),
        2048, dklen=64)


def chave_de(frase, senha=""):
    """A chave privada do Tempest derivada da frase.

    A BIP-32 usaria HMAC-SHA512 com a chave "Bitcoin seed" e seguiria
    derivando filhos. Aqui paramos no primeiro passo dela, que ja basta
    para uma chave so, e reduzimos modulo a ordem da curva.
    """
    bruto = hmac.new(b"Tempest seed", semente_de(frase, senha),
                     hashlib.sha512).digest()
    k = int.from_bytes(bruto[:32], "big") % ORDEM
    return k if k != 0 else 1
