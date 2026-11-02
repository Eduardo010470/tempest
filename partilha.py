# -*- coding: utf-8 -*-
"""Partilha de Shamir: quebra a semente em pedacos, e so k deles a refazem.

O dilema de guardar segredo: as doze palavras num papel so queimam num
incendio; num cofre, dependem do cofre; em duas copias, o risco de vazar
dobra. Toda copia a mais protege contra perda e expoe mais a roubo, e nao
da para melhorar os dois lados ao mesmo tempo. Parece uma lei da natureza.

Nao e. Adi Shamir resolveu isso em 1979, e a solucao e uma curiosidade de
colegial: por dois pontos passa uma e so uma reta; por tres pontos, uma e
so uma parabola; por k pontos, um e so um polinomio de grau k-1.

Entao: escondo o segredo no termo constante de um polinomio de grau k-1,
sorteio os outros coeficientes, e distribuo PONTOS da curva. Com k pontos
qualquer pessoa reconstroi o polinomio e le o termo constante. Com k-1,
nao. E agora o segredo esta em cinco lugares e nenhum deles o contem.

O "nao" aqui e de uma qualidade diferente de todo o resto da criptografia.
Senha fraca cai com computador suficiente. Curva eliptica cai com tempo
suficiente. Aqui nao ha o que atacar: com k-1 pontos, para CADA segredo
possivel existe exatamente um polinomio que passa por aqueles pontos com
aquele segredo. Todos igualmente compativeis, todos igualmente provaveis.
A informacao nao foi escondida — ela nao esta la. Shannon chamou isso de
sigilo perfeito, e e a mesma propriedade do bloco de uso unico.

    python3 partilha.py provar

mostra isso acontecendo, com numeros.

A conta roda num corpo finito, inteiros modulo um primo. Com numeros reais
nao funcionaria: os arredondamentos e a magnitude dos coeficientes
vazariam informacao sobre o tamanho do segredo. O primo aqui e 2^128 + 51,
o menor acima de 2^128, porque a entropia de uma frase de doze palavras
tem exatamente 128 bits.

Uso:
    python3 partilha.py repartir [k] [n]      padrao 3 de 5
    python3 partilha.py mostrar <numero>      le um pedaco por vez
    python3 partilha.py juntar <ped> <ped> <ped>
    python3 partilha.py provar
"""
import hashlib
import json
import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import curva
import semente

PRIMO = 2 ** 128 + 51
ARQ_CARTEIRA = "carteira.json"


# ------------------------------------------------------------- a matematica

def _inverso(a):
    """1/a no corpo. Fermat: a^(p-2) = a^-1 quando p e primo."""
    return pow(a % PRIMO, PRIMO - 2, PRIMO)


def _avalia(coef, x):
    """Horner: avalia o polinomio em x, de tras para frente."""
    y = 0
    for c in reversed(coef):
        y = (y * x + c) % PRIMO
    return y


def reparte(segredo, k, n):
    """Devolve n pontos do polinomio; k deles bastam para voltar."""
    if not 2 <= k <= n <= 99:
        raise ValueError("precisa de 2 <= k <= n <= 99")
    if not 0 <= segredo < PRIMO:
        raise ValueError("segredo fora do corpo")
    # o termo constante E o segredo; o resto e sorteio de verdade
    coef = [segredo] + [secrets.randbelow(PRIMO) for _ in range(k - 1)]
    return [(i, _avalia(coef, i)) for i in range(1, n + 1)]


def junta(pontos):
    """Interpolacao de Lagrange avaliada em x = 0, que e o termo constante.

    Para cada ponto, monta o polinomio que vale 1 nele e 0 em todos os
    outros, pesa pelo y daquele ponto, e soma. Em x = 0 isso devolve o
    termo constante do unico polinomio que passa por todos eles.
    """
    if len({x for x, _ in pontos}) != len(pontos):
        raise ValueError("ha pedacos repetidos — precisa de pedacos distintos")
    total = 0
    for i, (xi, yi) in enumerate(pontos):
        num, den = 1, 1
        for j, (xj, _) in enumerate(pontos):
            if i == j:
                continue
            num = num * (-xj) % PRIMO
            den = den * (xi - xj) % PRIMO
        total = (total + yi * num % PRIMO * _inverso(den)) % PRIMO
    return total


# -------------------------------------------------- escrever e ler o pedaco

def escreve(ponto):
    """Texto do pedaco, com soma de verificacao para pegar erro de copia."""
    i, y = ponto
    corpo = "%02d%033x" % (i, y)
    return "TEMPEST-%s-%s" % (corpo, hashlib.sha256(
        corpo.encode()).hexdigest()[:6])


def le(texto):
    """Devolve (indice, valor) ou levanta erro dizendo o que esta errado."""
    t = texto.strip().upper().replace(" ", "")
    if not t.startswith("TEMPEST-") or t.count("-") != 2:
        raise ValueError("isto nao tem o formato de um pedaco: %r" % texto)
    _, corpo, soma = t.split("-")
    if len(corpo) != 35:
        raise ValueError("o pedaco tem %d caracteres no miolo, esperado 35"
                         % len(corpo))
    corpo = corpo.lower()
    if hashlib.sha256(corpo.encode()).hexdigest()[:6] != soma.lower():
        raise ValueError("a soma de verificacao nao fecha — alguma letra ou "
                         "digito foi copiado errado neste pedaco")
    return int(corpo[:2], 10), int(corpo[2:], 16)


# -------------------------------------------------------- semente <-> bytes

def entropia_da_frase(frase):
    """Desfaz a BIP-39: das doze palavras de volta aos 128 bits que as geraram."""
    ok, motivo = semente.confere_frase(frase)
    if not ok:
        raise ValueError(motivo)
    indice = {p: i for i, p in enumerate(semente.palavras())}
    partes = semente.normaliza(frase).split()
    total = len(partes) * 11
    n_soma = total // 33
    inteiro = 0
    for p in partes:
        inteiro = (inteiro << 11) | indice[p]
    return (inteiro >> n_soma).to_bytes((total - n_soma) // 8, "big")


# -------------------------------------------------------------------- cli

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "ajuda"

    if cmd == "repartir":
        k = int(sys.argv[2]) if len(sys.argv) > 2 else 3
        n = int(sys.argv[3]) if len(sys.argv) > 3 else 5
        if not os.path.exists(ARQ_CARTEIRA):
            print("nao achei", ARQ_CARTEIRA, "nesta pasta."); return
        d = json.load(open(ARQ_CARTEIRA))
        if "frase" not in d:
            print("esta carteira nao tem frase de doze palavras — foi criada")
            print("antes da semente existir, e nao ha o que repartir.")
            return
        ent = entropia_da_frase(d["frase"])
        pontos = reparte(int.from_bytes(ent, "big"), k, n)

        # conferencia imediata: k pedacos quaisquer tem que voltar ao mesmo
        from itertools import combinations
        for tres in combinations(pontos, k):
            if junta(list(tres)) != int.from_bytes(ent, "big"):
                print("ERRO: a reconstrucao falhou, nada foi gravado."); return

        for i, p in pontos:
            nome = "pedaco-%d.txt" % i
            with open(nome, "w") as f:
                f.write(escreve((i, p)) + "\n")
            os.chmod(nome, 0o600)

        print("Reparti a sua semente em %d pedacos. Quaisquer %d a refazem;"
              % (n, k))
        print("%d ou menos nao dizem absolutamente nada.\n" % (k - 1))
        print("Gravei um arquivo por pedaco, e NAO os mostrei na tela —")
        print("tres pedacos juntos numa tela sao a sua carteira inteira.")
        print("Leia um de cada vez, copie no papel, e guarde em lugares")
        print("diferentes:\n")
        for i, _ in pontos:
            print("    python3 partilha.py mostrar %d" % i)
        print("\nDepois de copiados todos, apague os arquivos:")
        print("    rm pedaco-*.txt")
        print("\nConferi antes de gravar: todas as %d combinacoes possiveis"
              % len(list(combinations(pontos, k))))
        print("de %d pedacos reconstroem a semente certa." % k)

    elif cmd == "mostrar":
        i = int(sys.argv[2])
        nome = "pedaco-%d.txt" % i
        if not os.path.exists(nome):
            print("nao existe", nome); return
        print("\n   " + open(nome).read().strip() + "\n")
        print("copie no papel, confira caractere por caractere, e guarde")
        print("longe dos outros pedacos.")

    elif cmd == "juntar":
        textos = sys.argv[2:]
        if len(textos) < 2:
            print('uso: python3 partilha.py juntar "TEMPEST-..." "TEMPEST-..." ...')
            return
        try:
            pontos = [le(t) for t in textos]
        except ValueError as e:
            print("recusado:", e); return
        frase = semente.frase_de(junta(pontos).to_bytes(16, "big"))
        print("juntei %d pedacos: %s\n" % (len(pontos),
              ", ".join("#%d" % i for i, _ in pontos)))
        print("   " + frase + "\n")

        # Um pedaco a menos nao produz erro: produz OUTRA frase, valida.
        # A soma de verificacao da BIP-39 e calculada a partir da entropia
        # que sair, entao ela sempre fecha e nunca avisa nada. O unico jeito
        # honesto de saber e comparar o endereco com o que se esperava.
        end = curva.endereco(curva.chave_publica(semente.chave_de(frase)))
        print("endereco desta frase:", end)
        if os.path.exists(ARQ_CARTEIRA):
            d = json.load(open(ARQ_CARTEIRA))
            if d.get("endereco") == end:
                print("CONFERE com a carteira desta pasta.\n")
                print("Para reinstalar em outra maquina:")
                print('   python3 cadeia.py restaurar "%s"' % frase)
                return
            print("NAO confere com a carteira desta pasta (%s)."
                  % d["endereco"])

        print("\nATENCAO. Se faltou pedaco, esta frase nao e um erro — e OUTRA")
        print("semente, legitima e vazia. A soma de verificacao das doze")
        print("palavras e calculada em cima do que saiu, entao ela sempre")
        print("fecha, e o programa nao tem como saber quantos pedacos eram")
        print("necessarios: isso nao esta escrito em lugar nenhum.")
        print("\nConfira pelo endereco acima. Se nao for o que voce esperava,")
        print("faltam pedacos ou um deles e de outra semente.")

    elif cmd == "provar":
        print("A afirmacao a provar: com k-1 pedacos, TODO segredo continua")
        print("possivel. Nao e dificil de descobrir — e indeterminado.\n")
        segredo = secrets.randbelow(PRIMO)
        pontos = reparte(segredo, 3, 5)
        p1, p2 = pontos[0], pontos[1]
        print("Segredo verdadeiro: %x" % segredo)
        print("Limiar 3. Vou usar so DOIS pedacos, os de indice 1 e 2.\n")
        print("Para cada palpite abaixo eu monto a parabola que passa pelos")
        print("dois pontos E tem aquele palpite como termo constante:\n")

        candidatos = [("o verdadeiro", segredo),
                      ("zero", 0),
                      ("o numero 42", 42),
                      ("um sorteado agora", secrets.randbelow(PRIMO))]
        for rotulo, s in candidatos:
            (x1, y1), (x2, y2) = p1, p2
            u1, u2 = (y1 - s) % PRIMO, (y2 - s) % PRIMO
            det = x1 * x2 % PRIMO * (x2 - x1) % PRIMO
            a1 = (u1 * x2 * x2 - u2 * x1 * x1) % PRIMO * _inverso(det) % PRIMO
            a2 = (x1 * u2 - x2 * u1) % PRIMO * _inverso(det) % PRIMO
            coef = [s, a1, a2]
            bate = _avalia(coef, x1) == y1 and _avalia(coef, x2) == y2
            print("  %-18s -> parabola existe e passa nos dois pontos: %s"
                  % (rotulo, "SIM" if bate else "nao"))

        print("\nTodas existem. Os dois pedacos nao preferem nenhum segredo a")
        print("nenhum outro, e isso vale para os 2^128 possiveis — nao ha")
        print("conta a fazer, nao ha forca bruta que ajude, nao ha computador")
        print("grande o bastante, porque nao falta poder de calculo: falta")
        print("informacao. Com o terceiro ponto, a parabola fica unica e so")
        print("uma delas sobrevive.\n")
        print("Conferindo o outro lado — tres pedacos quaisquer:")
        from itertools import combinations
        for tres in list(combinations(pontos, 3))[:4]:
            quais = ",".join(str(i) for i, _ in tres)
            print("  pedacos %-6s -> %s" % (quais,
                  "acertou" if junta(list(tres)) == segredo else "ERROU"))

    else:
        print(__doc__)


if __name__ == "__main__":
    main()
