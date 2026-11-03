# -*- coding: utf-8 -*-
"""Rede do Tempest: faz dois ou mais nos conversarem.

Aqui nasce o unico problema que importa numa blockchain. Com um no so,
quem escreve a cadeia e dono dela. Com dois, eles podem discordar — e
nao existe arbitro. A regra que resolve o empate e esta:

    vence a cadeia valida com mais trabalho acumulado

Como a dificuldade do Tempest varia, "mais trabalho" nao e o mesmo que
"mais blocos": um bloco de 6 zeros custou dezesseis vezes mais que um de
5. Por isso a conta e a soma do trabalho de cada bloco, igual ao Bitcoin.

Repara no que a regra implica: quem tiver mais poder de computacao que
todo o resto junto escreve a historia. A seguranca nao vem da
criptografia — vem de ser caro demais juntar esse poder.

Duas coisas que todo no de verdade faz, e este faz:

  REORGANIZACAO. Quando a cadeia de fora ganha, os blocos meus que ela
  nao tem sao descartados — e as transacoes que estavam dentro deles
  nao podem simplesmente evaporar. Elas voltam para a fila e brigam por
  um lugar nos blocos novos. E dai que vem a regra pratica de esperar
  confirmacoes: a sua transacao nao esta firme por estar num bloco, esta
  firme quando desfazer o bloco dela ficou caro demais.

  DESCOBERTA. Um no guarda a lista de quem ele conhece e troca essa
  lista com quem encontra. Voce apresenta ele a UM par; o resto ele
  descobre sozinho. E assim que uma rede cresce sem ninguem no centro.

  SEMENTE. Um no recem-instalado nao conhece ninguem, e nao existe
  jeito de descobrir por conta propria quem esta no ar. Entao a lista
  comeca escrita no codigo: PARES_SEMENTE. E a unica parte de uma
  blockchain que nao e matematica — um endereco que alguem precisa
  manter de pe. O Bitcoin tem cinco desses e nunca conseguiu se livrar
  de nenhum.

  Mas repara no que o no semente NAO pode fazer. Nao pode mentir sobre
  a cadeia, porque a genese e constante e a validacao e integral: se ele
  mandar outra historia, ela e recusada. Nao pode inventar pares, porque
  quem ele indica se apresenta sozinho ou nao e falado com. O pior que
  um no semente consegue fazer e nao responder.

Variaveis de ambiente, para rodar num servidor:
    PORT                 a porta (o Railway e o Heroku definem sozinhos)
    TEMPEST_EU           como este no se apresenta, se nao der para deduzir
    TEMPEST_SEMENTE      pares semente extras, separados por virgula
    TEMPEST_RODADA       segundos entre rodadas automaticas (0 desliga)
    TEMPEST_DIR          pasta do estado, para um volume montado

Uso:
    python3 no.py sou http://MEU_IP:5000     como eu me apresento
    python3 no.py servir 5000                poe este no no ar
    python3 no.py conhecer http://IP:5000    apresenta este no a um par
    python3 no.py pares                      quem eu conheco
    python3 no.py rodada                     conversa com todos os pares
    python3 no.py estado http://IP:5000      ve como o outro esta
    python3 no.py sincronizar http://IP:5000 puxa de um so
    python3 no.py espalhar http://IP:5000    empurra para um so
"""
import json
import os
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cadeia as C

ARQ_PARES = "pares.json"
MAX_PARES = 40
MAX_CORPO = 8 * 1024 * 1024      # teto do POST

# Os nos que um no recem-instalado conhece sem ninguem apresentar.
# Enquanto estiver vazio, cada no precisa de um 'conhecer' na mao.
PARES_SEMENTE = [
    "https://web-production-a3ca95.up.railway.app",
]
PARES_SEMENTE += [p.strip() for p in
                  os.environ.get("TEMPEST_SEMENTE", "").split(",") if p.strip()]

def inteiro(nome, padrao):
    """Le um numero do ambiente sem derrubar o processo.

    Um 'TEMPEST_RODADA=60=' ja matou este no: int('60=') levanta
    ValueError, e o no morreu antes de abrir a porta. Num processo que
    roda sozinho num servidor, variavel mal digitada tem que virar AVISO,
    nao morte — ninguem esta olhando para reiniciar.

    E nao tenta consertar o que foi escrito. Nada de tirar o '=' e supor
    que a pessoa queria 60: um no que adivinha a intencao do operador e
    pior que um que recusa e diz o que recusou.
    """
    bruto = (os.environ.get(nome) or "").strip()
    if not bruto:
        return padrao
    try:
        return int(bruto)
    except ValueError:
        print("aviso: %s=%r nao e um numero inteiro. seguindo com %d."
              % (nome, bruto, padrao))
        return padrao


# Uma tranca so, para a cadeia e para a fila. Enquanto o no atendia um
# cliente de cada vez ela nao fazia falta. Agora faz: dois POST /cadeia
# simultaneos leem o mesmo arquivo, decidem cada um por si, e o ultimo a
# gravar apaga a decisao do outro. E reentrante porque decide() chama
# junta_pendentes() por dentro, na reorganizacao.
TRANCA = threading.RLock()


def trabalho(cadeia):
    """Soma do custo de cada bloco. Um zero a mais vale 16 vezes mais."""
    return sum(16 ** C.dificuldade_em(cadeia, b["indice"]) for b in cadeia)


# ------------------------------------------------------------------ pares

def carrega_pares():
    if os.path.exists(ARQ_PARES):
        d = json.load(open(ARQ_PARES))
        return d.get("eu"), list(d.get("pares", []))
    return None, []


def grava_pares(eu, lista):
    limpos = []
    for p in lista:
        p = (p or "").strip().rstrip("/")
        if p.startswith("http") and p != (eu or "") and p not in limpos:
            limpos.append(p)
    limpos = limpos[:MAX_PARES]
    C.grava(ARQ_PARES, {"eu": eu, "pares": limpos})
    return limpos


def aprende_pares(novos, eu_deles=None):
    """Mistura a lista de fora com a minha. E o gossip, em tres linhas."""
    eu, meus = carrega_pares()
    antes = len(meus)
    agora = grava_pares(eu, meus + list(novos or [])
                        + ([eu_deles] if eu_deles else []))
    return {"conhecidos": len(agora), "novos": len(agora) - antes}


# --------------------------------------------------------------- consenso

def junta_pendentes(vindas):
    with TRANCA:
        return _junta_pendentes(vindas)


def _junta_pendentes(vindas):
    """Mistura a fila de fora com a minha, sem repetir e sem aceitar lixo.

    Tres filtros, e cada um existe por um motivo diferente. O primeiro
    corta o que eu ja tenho. O segundo corta assinatura invalida — nao
    gasto banda com quem nao sabe assinar. O terceiro e o importante: a
    transacao pode estar perfeitamente assinada e ainda assim ser uma
    REPETICAO de algo que a minha cadeia ja confirmou. Esse e o ataque
    que a sequencia impede, e recusar aqui na porta e melhor que recusar
    depois: a transacao morre antes de entrar na fila e nunca chega a
    ser espalhada por mim para os outros nos.
    """
    minhas = C.carrega_pendentes()
    gastas = C.sequencias(C.carrega_cadeia())
    vistas = {C.id_tx(tx) for tx in minhas}
    novas, repetidas, invalidas = 0, 0, 0
    for tx in vindas:
        if C.id_tx(tx) in vistas:
            continue
        if not C.tx_valida(tx):
            invalidas += 1
            continue
        if tx["seq"] < gastas.get(C.remetente(tx), 0):
            repetidas += 1
            continue
        minhas.append(tx)
        vistas.add(C.id_tx(tx))
        novas += 1
    C.grava_pendentes(minhas)
    return {"recebidas": len(vindas), "novas": novas,
            "repetidas": repetidas, "invalidas": invalidas,
            "fila": len(minhas)}


def decide(forasteira):
    with TRANCA:
        return _decide(forasteira)


def _decide(forasteira):
    """O coracao do consenso: so adota quem ganha em trabalho E e valida."""
    minha = C.carrega_cadeia()
    tm, tf = trabalho(minha), trabalho(forasteira)
    if tf <= tm:
        return {"adotou": False, "motivo": "a minha tem trabalho igual ou maior",
                "meu_trabalho": tm, "trabalho_dela": tf,
                "meus_blocos": len(minha), "blocos_dela": len(forasteira)}
    ok, motivo = C.valida(forasteira)
    if not ok:
        return {"adotou": False, "motivo": "a de fora e invalida: " + motivo}

    # ---- reorganizacao: salvar as transacoes dos blocos que vao morrer
    ids_fora = {C.id_tx(t) for b in forasteira for t in b["transacoes"]}
    orfas = [t for b in minha for t in b["transacoes"]
             if t.get("de") is not None and C.id_tx(t) not in ids_fora]

    C.grava_cadeia(forasteira)

    r = {"adotou": True, "motivo": "cadeia com mais trabalho e valida",
         "antes": len(minha), "agora": len(forasteira),
         "trabalho_antes": tm, "trabalho_agora": tf}
    if orfas:
        # agora que a cadeia nova esta no lugar, a fila as julga contra ela:
        # as que a cadeia nova ja confirmou por outro caminho sao recusadas
        # como repeticao; as demais voltam para a fila e serao mineradas.
        volta = junta_pendentes(orfas)
        r["orfas"] = len(orfas)
        r["devolvidas_a_fila"] = volta["novas"]
        r["ja_confirmadas_na_nova"] = volta["repetidas"]
    return r


# -------------------------------------------------------------- servidor

class No(BaseHTTPRequestHandler):

    def _envia(self, codigo, obj):
        corpo = json.dumps(obj).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        if self.path == "/cadeia":
            self._envia(200, C.carrega_cadeia())
        elif self.path == "/pendentes":
            self._envia(200, C.carrega_pendentes())
        elif self.path == "/pares":
            eu, pares = carrega_pares()
            self._envia(200, {"eu": eu, "pares": pares})
        elif self.path == "/estado":
            c = C.carrega_cadeia()
            ok, motivo = C.valida(c)
            eu, pares = carrega_pares()
            self._envia(200, {"rede": C.NOME, "eu": eu, "blocos": len(c),
                              "trabalho": trabalho(c), "valida": ok,
                              "motivo": motivo, "fila": len(C.carrega_pendentes()),
                              "pares": len(pares), "topo": c[-1]["hash"]})
        else:
            self._envia(404, {"erro": "rota desconhecida"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        if n > MAX_CORPO:
            # um Content-Length mentiroso derrubaria o processo por memoria
            return self._envia(413, {"erro": "corpo grande demais"})
        try:
            corpo = json.loads(self.rfile.read(n))
        except Exception:
            return self._envia(400, {"erro": "json invalido"})
        if self.path == "/cadeia":
            self._envia(200, decide(corpo))
        elif self.path == "/pendentes":
            self._envia(200, junta_pendentes(corpo))
        elif self.path == "/pares":
            aprende_pares(corpo.get("pares"), corpo.get("eu"))
            eu, pares = carrega_pares()
            self._envia(200, {"eu": eu, "pares": pares})
        else:
            self._envia(404, {"erro": "rota desconhecida"})

    def log_message(self, *a):
        pass


def busca(url, rota, corpo=None):
    req = urllib.request.Request(
        url.rstrip("/") + rota,
        data=None if corpo is None else json.dumps(corpo).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def conversa(par):
    """Uma conversa completa com um par: pares, cadeia e fila, nos dois sentidos."""
    eu, meus = carrega_pares()
    d = busca(par, "/pares", {"eu": eu, "pares": meus})
    aprendi = aprende_pares(d.get("pares"), d.get("eu"))
    puxei = decide(busca(par, "/cadeia"))
    fila = junta_pendentes(busca(par, "/pendentes"))
    empurrei = busca(par, "/cadeia", C.carrega_cadeia())
    busca(par, "/pendentes", C.carrega_pendentes())
    return {"pares": aprendi, "puxei": puxei, "fila": fila,
            "o_outro_adotou_a_minha": empurrei.get("adotou")}


def laco_rodadas(intervalo):
    """O no nao fica so esperando: tambem vai atras.

    Um no que apenas atende e um mural — recebe o que empurram e nunca
    busca. Basta perder uma conexao na hora errada para ficar atras e
    nunca mais descobrir sozinho. Qualquer erro aqui e engolido de
    proposito: a rodada e oportunista, e um par fora do ar nao e motivo
    para derrubar o no.
    """
    time.sleep(5)
    while True:
        for p in list(carrega_pares()[1]):
            try:
                conversa(p)
            except Exception:
                pass
        time.sleep(intervalo)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "ajuda"

    if cmd == "sou":
        _, meus = carrega_pares()
        meu = sys.argv[2].rstrip("/")
        grava_pares(meu, meus)
        print("vou me apresentar aos outros como", meu)
        print("use o IP que os outros alcancam, nao 127.0.0.1")

    elif cmd == "servir":
        if os.environ.get("TEMPEST_DIR"):
            os.chdir(os.environ["TEMPEST_DIR"])
        porta = inteiro("PORT",
                        int(sys.argv[2]) if len(sys.argv) > 2 else 5000)

        # como este no se apresenta. num servidor isso nao pode ser
        # digitado a mao, e o Railway publica o dominio no ambiente.
        eu, pares = carrega_pares()
        eu = os.environ.get("TEMPEST_EU") or eu
        dominio = os.environ.get("RAILWAY_PUBLIC_DOMAIN")
        if not eu and dominio:
            eu = "https://" + dominio.strip().rstrip("/")
        pares = grava_pares(eu, pares + PARES_SEMENTE)

        c = C.carrega_cadeia()
        if len(c) == 1 and pares:
            # cadeia vazia e pares conhecidos: puxa antes de abrir a porta.
            # um no recem-criado (ou que perdeu o disco) nao precisa de
            # backup — a genese e constante, e a cadeia de verdade esta
            # com quem tem mais trabalho.
            for p in pares:
                try:
                    decide(busca(p, "/cadeia"))
                except Exception:
                    pass
            c = C.carrega_cadeia()

        print("no %s no ar em http://0.0.0.0:%d  (ctrl-c para parar)"
              % (C.NOME, porta))
        print("me apresento como:", eu or "(nada — rode 'no.py sou URL')")
        print("conheco %d par(es), tenho %d bloco(s)" % (len(pares), len(c)))
        print("rotas: GET /estado /cadeia /pendentes /pares"
              " | POST /cadeia /pendentes /pares")

        intervalo = inteiro("TEMPEST_RODADA", 0)
        if intervalo > 0:
            threading.Thread(target=laco_rodadas, args=(intervalo,),
                             daemon=True).start()
            print("rodada automatica a cada %d s" % intervalo)

        # Threading, nao HTTPServer: um cliente lento travava todos os
        # outros, e com a rodada de fundo o no agora e cliente de si mesmo.
        ThreadingHTTPServer(("0.0.0.0", porta), No).serve_forever()

    elif cmd == "conhecer":
        url = sys.argv[2].rstrip("/")
        aprende_pares([url])
        print(json.dumps(conversa(url), indent=1))
        print("\nagora conheco:", carrega_pares()[1])

    elif cmd == "pares":
        eu, pares = carrega_pares()
        print("eu sou:", eu or "(nao me apresentei)")
        if not pares:
            print("nao conheco ninguem. comece com: no.py conhecer http://IP:PORTA")
        for p in pares:
            try:
                d = busca(p, "/estado")
                print("  %-28s %d blocos, trabalho %d, fila %d, %d pares"
                      % (p, d["blocos"], d["trabalho"], d["fila"], d["pares"]))
            except Exception as e:
                print("  %-28s sem resposta (%s)" % (p, e.__class__.__name__))

    elif cmd == "rodada":
        eu, pares = carrega_pares()
        if not pares and PARES_SEMENTE:
            pares = grava_pares(eu, PARES_SEMENTE)
            print("nao conhecia ninguem; usei os pares semente do codigo.")
        if not pares:
            print("nao conheco ninguem ainda.")
            print("comece com: python3 no.py conhecer http://IP:PORTA")
            return
        for p in list(pares):
            print("--", p)
            try:
                r = conversa(p)
                print("   pares:", json.dumps(r["pares"]))
                print("   puxei:", r["puxei"].get("motivo"),
                      "| adotou:", r["puxei"].get("adotou"))
                if r["puxei"].get("orfas"):
                    print("   REORG: %d orfa(s), %d de volta para a fila"
                            % (r["puxei"]["orfas"],
                               r["puxei"]["devolvidas_a_fila"]))
                print("   fila:", json.dumps(r["fila"]))
                print("   ele adotou a minha:", r["o_outro_adotou_a_minha"])
            except Exception as e:
                print("   sem resposta:", e.__class__.__name__, e)
        print("\nconheco %d par(es) agora" % len(carrega_pares()[1]))

    elif cmd == "sincronizar":
        url = sys.argv[2]
        print(json.dumps(decide(busca(url, "/cadeia")), indent=1))
        print(json.dumps(junta_pendentes(busca(url, "/pendentes")), indent=1))

    elif cmd == "espalhar":
        url = sys.argv[2]
        print(json.dumps(busca(url, "/cadeia", C.carrega_cadeia()), indent=1))
        print(json.dumps(busca(url, "/pendentes", C.carrega_pendentes()), indent=1))

    elif cmd == "estado":
        print(json.dumps(busca(sys.argv[2], "/estado"), indent=1))

    else:
        print(__doc__)


if __name__ == "__main__":
    main()
