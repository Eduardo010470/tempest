# -*- coding: utf-8 -*-
"""A tela do Tempest: a carteira no navegador, servida pelo proprio no.

    python3 tela.py          e abra http://127.0.0.1:5050 no navegador

Por que isto e um programa separado do `no.py`: estas rotas ASSINAM com a
sua chave privada e MINERAM para o seu endereco. O `no.py` atende a rede
inteira em 0.0.0.0, e nele isso seria um convite — qualquer um no mesmo
wi-fi gastaria as suas moedas. Aqui o servidor se amarra em 127.0.0.1 e
nao atende ninguem de fora da propria maquina. Nao mude isso.

A pagina nao tem dependencia nenhuma: um arquivo, sem CDN, sem fonte
baixada, sem framework. Funciona com o aviao ligado.
"""
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cadeia as C

ENDERECO = "127.0.0.1"
PORTA = 5050


# --------------------------------------------------------------- a pagina

PAGINA = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tempest</title>
<style>
  :root {
    --breu:   #11161f;
    --casco:  #1a212c;
    --linha:  #2b3442;
    --texto:  #dfe5ee;
    --fraco:  #7e8b9e;
    --raio:   #8fd4ff;
    --brasa:  #e8a33d;
    --mono: ui-monospace, "SF Mono", "Roboto Mono", "DejaVu Sans Mono", monospace;
    --sans: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; background: var(--breu); color: var(--texto); }
  body { font: 15px/1.6 var(--sans); -webkit-text-size-adjust: 100%; }
  main { max-width: 560px; margin: 0 auto; padding: 22px 18px 72px; }

  .topo { display: flex; align-items: baseline; justify-content: space-between;
          gap: 12px; padding-bottom: 20px; }
  .topo h1 { margin: 0; font-size: 17px; font-weight: 620;
             letter-spacing: -.2px; }
  .topo h1 span { color: var(--fraco); font-weight: 400; }
  .vivo { font: 12px/1 var(--mono); color: var(--fraco); }
  .vivo b { color: var(--texto); font-weight: 500; }

  /* o heroi: o hash do topo da cadeia, com os zeros que custaram trabalho */
  .pow { padding: 6px 0 22px; border-bottom: 1px solid var(--linha); }
  .hash { font: 400 clamp(19px, 7.4vw, 27px)/1.35 var(--mono);
          word-break: break-all; color: #4e5a6c; letter-spacing: -.5px; }
  .hash i { font-style: normal; color: var(--raio); }
  .custo { margin: 12px 0 0; color: var(--fraco); font-size: 13.5px; }
  .custo b { color: var(--texto); font-weight: 500; }

  .saldo { padding: 22px 0; border-bottom: 1px solid var(--linha); }
  .n { font: 300 42px/1 var(--sans); letter-spacing: -1.6px; }
  .n em { font-style: normal; font-size: 17px; font-weight: 500;
          color: var(--fraco); letter-spacing: 0; margin-left: 7px; }
  .meu { margin: 13px 0 0; font: 12.5px/1.55 var(--mono); color: var(--fraco);
         word-break: break-all; }
  .meu button { background: none; border: 0; color: var(--raio); padding: 0;
                font: inherit; cursor: pointer; }
  .seq { margin: 5px 0 0; font: 12.5px/1.5 var(--mono); color: var(--fraco); }

  .zona { padding: 20px 0; border-bottom: 1px solid var(--linha); }
  .zona h2 { margin: 0 0 13px; font-size: 13.5px; font-weight: 560;
             color: var(--fraco); }

  button.acao { width: 100%; padding: 14px; border-radius: 9px;
    border: 1px solid var(--linha); background: var(--casco);
    color: var(--texto); font: 500 15px var(--sans); cursor: pointer; }
  button.acao:hover { border-color: #3b4756; }
  button.acao:disabled { color: var(--fraco); cursor: default; }
  button.acao:focus-visible, input:focus-visible { outline: 2px solid var(--raio);
    outline-offset: 2px; }

  .achado { margin: 13px 0 0; padding: 13px 14px; border-radius: 9px;
    background: #20242b; border-left: 2px solid var(--brasa);
    font: 13px/1.6 var(--mono); color: #cfd6e2; word-break: break-all; }
  .achado b { color: var(--brasa); font-weight: 500; }
  .erro { border-left-color: #d9684f; }
  .erro b { color: #ef8f78; }

  form { display: grid; gap: 9px; }
  input { width: 100%; padding: 12px 13px; border-radius: 9px;
    border: 1px solid var(--linha); background: #141a24; color: var(--texto);
    font: 14px var(--mono); }
  input::placeholder { color: #5b667a; }
  .dupla { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; }
  .dupla label { display: grid; gap: 5px; font: 12.5px var(--sans);
                 color: var(--fraco); }

  .barra { height: 3px; background: var(--linha); border-radius: 2px;
           overflow: hidden; margin: 10px 0 9px; }
  .barra div { height: 100%; background: var(--raio); }
  .legenda { font: 12.5px/1.5 var(--mono); color: var(--fraco); }

  table { width: 100%; border-collapse: collapse; font: 12.5px var(--mono); }
  td { padding: 8px 0; border-top: 1px solid #202835; vertical-align: middle; }
  tr:first-child td { border-top: 0; }
  td.i { color: var(--fraco); width: 3.4em; }
  td.z { width: 5.6em; }
  td.z s { display: inline-block; width: 4px; height: 11px; margin-right: 2px;
           background: var(--raio); text-decoration: none; border-radius: 1px; }
  td.h { color: #5d6878; }
  td.t { text-align: right; color: var(--fraco); white-space: nowrap; }
  .fluxo td.v { text-align: right; white-space: nowrap; }
  .fluxo .mais { color: var(--raio); }
  .vazio { color: var(--fraco); font-size: 13.5px; margin: 0; }

  .pe { padding-top: 20px; color: #5f6b7d; font-size: 12px; line-height: 1.7; }
  .pe code { font: 11.5px var(--mono); color: var(--fraco); }
  @media (prefers-reduced-motion: no-preference) {
    .cavando { animation: pulsa 1.1s ease-in-out infinite; }
    @keyframes pulsa { 50% { opacity: .45 } }
  }
</style>
</head>
<body>
<main>

  <div class="topo">
    <h1>Tempest <span>TEMP</span></h1>
    <div class="vivo" id="vivo"></div>
  </div>

  <div class="pow">
    <div class="hash" id="hash">carregando</div>
    <p class="custo" id="custo"></p>
  </div>

  <div class="saldo">
    <div class="n"><span id="saldo">0</span><em>TEMP</em></div>
    <p class="meu"><span id="meu"></span>
      <button id="copiar" type="button">copiar</button></p>
    <p class="seq">próxima transação que vou assinar: nº <span id="seq">0</span></p>
  </div>

  <div class="zona">
    <button class="acao" id="minerar" type="button">Minerar um bloco</button>
    <div id="retorno"></div>
  </div>

  <div class="zona">
    <h2>Enviar</h2>
    <form id="envio">
      <input id="para" placeholder="endereço de destino, 40 caracteres"
             autocomplete="off" spellcheck="false" inputmode="latin">
      <div class="dupla">
        <label>valor<input id="valor" inputmode="numeric" placeholder="0"></label>
        <label>taxa para quem minerar<input id="taxa" inputmode="numeric" value="1"></label>
      </div>
      <button class="acao" type="submit">Assinar e pôr na fila</button>
    </form>
    <div id="recibo"></div>
  </div>

  <div class="zona">
    <h2>Emissão</h2>
    <div class="barra"><div id="emibarra" style="width:0"></div></div>
    <p class="legenda" id="emissao"></p>
  </div>

  <div class="zona">
    <h2>Meu dinheiro, bloco por bloco</h2>
    <table class="fluxo"><tbody id="fluxo"></tbody></table>
    <p class="vazio" id="semfluxo" hidden>Nada ainda. Minere um bloco.</p>
  </div>

  <div class="zona">
    <h2>A cadeia</h2>
    <table><tbody id="blocos"></tbody></table>
  </div>

  <p class="pe">
    Esta tela só responde a <code>127.0.0.1</code> — ela assina com a sua
    chave privada, e ninguém fora deste aparelho fala com ela.
    As doze palavras não passam por aqui: <code>python3 cadeia.py semente</code>.
  </p>

</main>
<script>
const $ = s => document.querySelector(s);
const curto = h => h.slice(0, 10) + "…" + h.slice(-6);

function zeros(hash) {
  let n = 0;
  while (hash[n] === "0") n++;
  return n;
}

function pintaHash(hash) {
  const n = zeros(hash);
  return "<i>" + hash.slice(0, n) + "</i>" + hash.slice(n);
}

let estado = null;

async function carrega() {
  const r = await fetch("/api/estado");
  estado = await r.json();
  const e = estado;

  $("#vivo").innerHTML = "<b>" + e.blocos + "</b> blocos · fila <b>"
    + e.fila + "</b>" + (e.valida ? "" : " · cadeia inválida");

  const topo = e.ultimos[0];
  $("#hash").innerHTML = pintaHash(topo.hash);
  const nz = zeros(topo.hash);
  $("#custo").innerHTML = "Bloco <b>" + topo.indice + "</b>. "
    + "A regra pedia <b>" + topo.dificuldade + "</b> zeros; este hash abre com "
    + "<b>" + nz + "</b>, achado na tentativa <b>"
    + topo.nonce.toLocaleString("pt-BR") + "</b>.";

  $("#saldo").textContent = e.saldo.toLocaleString("pt-BR");
  $("#meu").textContent = e.endereco;
  $("#seq").textContent = e.sequencia;

  const pct = 100 * e.emitido / e.teto;
  $("#emibarra").style.width = pct.toFixed(1) + "%";
  $("#emissao").innerHTML = e.emitido + " de " + e.teto + " TEMP criados ("
    + pct.toFixed(1) + "%) · recompensa agora " + e.recompensa
    + " · próximo halving no bloco " + e.halving;

  $("#fluxo").innerHTML = e.minhas.map(m =>
    "<tr><td class='i'>#" + m.bloco + "</td>"
    + "<td>" + m.tipo + (m.outro ? " " + curto(m.outro) : "") + "</td>"
    + "<td class='v " + (m.valor > 0 ? "mais" : "") + "'>"
    + (m.valor > 0 ? "+" : "") + m.valor + "</td></tr>").join("");
  $("#semfluxo").hidden = e.minhas.length > 0;

  $("#blocos").innerHTML = e.ultimos.map(b =>
    "<tr><td class='i'>#" + b.indice + "</td>"
    + "<td class='z'>" + "<s></s>".repeat(b.dificuldade) + "</td>"
    + "<td class='h'>" + curto(b.hash) + "</td>"
    + "<td class='t'>" + b.transacoes + (b.transacoes === 1 ? " tx" : " txs")
    + "</td></tr>").join("");
}

$("#copiar").onclick = async () => {
  try {
    await navigator.clipboard.writeText(estado.endereco);
    $("#copiar").textContent = "copiado";
    setTimeout(() => ($("#copiar").textContent = "copiar"), 1600);
  } catch (_) {
    $("#copiar").textContent = "selecione à mão";
  }
};

$("#minerar").onclick = async () => {
  const b = $("#minerar");
  b.disabled = true;
  b.classList.add("cavando");
  b.textContent = "Procurando um nonce que dê os zeros…";
  $("#retorno").innerHTML = "";
  try {
    const r = await fetch("/api/minerar", { method: "POST" });
    const d = await r.json();
    if (d.erro) {
      $("#retorno").innerHTML = "<div class='achado erro'><b>Não deu.</b> "
        + d.erro + "</div>";
    } else {
      $("#retorno").innerHTML = "<div class='achado'><b>Bloco " + d.indice
        + " é seu.</b> " + d.dificuldade + " zeros em "
        + d.segundos.toFixed(1) + "s, tentativa "
        + d.nonce.toLocaleString("pt-BR") + ". Prêmio de " + d.premio
        + " TEMP, sendo " + d.emissao + " de emissão e " + d.taxas
        + " de taxas." + (d.recusadas
          ? " " + d.recusadas + " da fila foram descartadas: sequência já gasta."
          : "") + "</div>";
      await carrega();
    }
  } catch (err) {
    $("#retorno").innerHTML = "<div class='achado erro'><b>O nó não respondeu.</b>"
      + " Ele ainda está rodando no terminal?</div>";
  }
  b.disabled = false;
  b.classList.remove("cavando");
  b.textContent = "Minerar um bloco";
};

$("#envio").onsubmit = async ev => {
  ev.preventDefault();
  const corpo = {
    para: $("#para").value.trim(),
    valor: parseInt($("#valor").value, 10),
    taxa: parseInt($("#taxa").value, 10) || 0
  };
  const r = await fetch("/api/enviar", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(corpo)
  });
  const d = await r.json();
  if (d.erro) {
    $("#recibo").innerHTML = "<div class='achado erro'><b>Não assinei.</b> "
      + d.erro + "</div>";
  } else {
    $("#recibo").innerHTML = "<div class='achado'><b>Assinada como sequência "
      + d.seq + ".</b> Está na fila. Entra no próximo bloco que alguém minerar,"
      + " e a taxa de " + d.taxa + " vai para quem minerar.</div>";
    $("#para").value = ""; $("#valor").value = "";
    await carrega();
  }
};

carrega();
</script>
</body>
</html>
"""


# ----------------------------------------------------------------- estado

def proximo_halving(n):
    return (n // C.HALVING + 1) * C.HALVING


def meu_fluxo(cadeia, eu):
    """Cada entrada e saida do meu endereco, do bloco mais novo para o antigo."""
    saida = []
    for b in cadeia:
        for tx in b["transacoes"]:
            de = C.remetente(tx)
            if de is None and tx["para"] == eu:
                saida.append({"bloco": b["indice"], "tipo": "minerei",
                              "outro": None, "valor": tx["valor"]})
            elif de == eu:
                saida.append({"bloco": b["indice"], "tipo": "enviei para",
                              "outro": tx["para"],
                              "valor": -(tx["valor"] + tx["taxa"])})
            elif tx["para"] == eu:
                saida.append({"bloco": b["indice"], "tipo": "recebi de",
                              "outro": de, "valor": tx["valor"]})
    saida.reverse()
    return saida[:40]


def estado():
    priv, pub, eu, nova = C.carrega_carteira()
    cadeia = C.carrega_cadeia()
    ok, motivo = C.valida(cadeia)
    criado = sum(tx["valor"] for b in cadeia for tx in b["transacoes"]
                 if tx["de"] is None)
    ultimos = [{"indice": b["indice"], "hash": b["hash"], "nonce": b["nonce"],
                "transacoes": len(b["transacoes"]),
                "dificuldade": C.dificuldade_em(cadeia, b["indice"])}
               for b in reversed(cadeia[-14:])]
    return {
        "rede": C.NOME, "simbolo": C.SIMBOLO,
        "endereco": eu,
        "saldo": C.saldos(cadeia).get(eu, 0),
        "sequencia": C.sequencias(cadeia).get(eu, 0),
        "blocos": len(cadeia),
        "fila": len(C.carrega_pendentes()),
        "valida": ok, "motivo": motivo,
        "teto": C.teto(), "emitido": criado,
        "recompensa": C.recompensa_em(len(cadeia)),
        "halving": proximo_halving(len(cadeia)),
        "ultimos": ultimos,
        "minhas": meu_fluxo(cadeia, eu),
    }


def minerar():
    priv, pub, eu, _ = C.carrega_carteira()
    cadeia = C.carrega_cadeia()
    i = len(cadeia)
    pend = C.carrega_pendentes()
    s, q = C.saldos(cadeia), C.sequencias(cadeia)
    aceitas, mortas, adiadas = [], [], []
    for tx in sorted(pend, key=lambda t: t.get("seq", 0)):
        de = C.remetente(tx)
        if not C.tx_valida(tx) or tx["seq"] < q.get(de, 0):
            mortas.append(tx)
            continue
        custo = tx["valor"] + tx["taxa"]
        if tx["seq"] != q.get(de, 0) or s.get(de, 0) < custo:
            adiadas.append(tx)
            continue
        q[de] = q.get(de, 0) + 1
        s[de] -= custo
        s[tx["para"]] = s.get(tx["para"], 0) + tx["valor"]
        aceitas.append(tx)
    taxas = sum(t["taxa"] for t in aceitas)
    premio = C.recompensa_em(i) + taxas
    txs = list(aceitas)
    if premio > 0:
        txs.insert(0, {"de": None, "para": eu, "valor": premio, "taxa": 0,
                       "seq": None, "quando": time.time(), "assinatura": None})
    dif = C.dificuldade_em(cadeia, i)
    t0 = time.time()
    b = C.minera_bloco(i, cadeia[-1]["hash"], txs, dif,
                       piso=C.tempo_mediano(cadeia, i))
    cadeia.append(b)
    C.grava_cadeia(cadeia)
    C.grava_pendentes(adiadas)
    return {"indice": b["indice"], "hash": b["hash"], "nonce": b["nonce"],
            "dificuldade": dif, "segundos": time.time() - t0,
            "premio": premio, "emissao": C.recompensa_em(i), "taxas": taxas,
            "recusadas": len(mortas)}


def enviar(para, valor, taxa):
    priv, pub, eu, _ = C.carrega_carteira()
    cadeia = C.carrega_cadeia()
    if not isinstance(para, str) or len(para) != 40:
        return {"erro": "um endereço do Tempest tem 40 caracteres hexadecimais."}
    try:
        int(para, 16)
    except ValueError:
        return {"erro": "esse destino tem caracteres que não são hexadecimais."}
    if para == eu:
        return {"erro": "esse é o seu próprio endereço."}
    if not isinstance(valor, int) or valor <= 0:
        return {"erro": "o valor precisa ser um número inteiro maior que zero."}
    if not isinstance(taxa, int) or taxa < 0:
        return {"erro": "a taxa precisa ser zero ou mais."}
    pend = C.carrega_pendentes()
    comprometido = sum(t["valor"] + t["taxa"] for t in pend
                       if C.remetente(t) == eu)
    livre = C.saldos(cadeia).get(eu, 0) - comprometido
    if livre < valor + taxa:
        return {"erro": "você tem %d TEMP livres e isso custa %d."
                        % (livre, valor + taxa)}
    seq = (C.sequencias(cadeia).get(eu, 0)
           + sum(1 for t in pend if C.remetente(t) == eu))
    pend.append(C.cria_tx(priv, pub, para, valor, taxa, seq))
    C.grava_pendentes(pend)
    return {"seq": seq, "valor": valor, "taxa": taxa}


# -------------------------------------------------------------- servidor

class Tela(BaseHTTPRequestHandler):
    server_version = "Tempest"

    def _json(self, codigo, obj):
        corpo = json.dumps(obj).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _local(self):
        """Ninguem de fora desta maquina, nem por acidente de configuracao."""
        if self.client_address[0] not in ("127.0.0.1", "::1"):
            self._json(403, {"erro": "esta tela só atende a própria máquina"})
            return False
        return True

    def do_GET(self):
        if not self._local():
            return
        if self.path in ("/", "/index.html"):
            corpo = PAGINA.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(corpo)
        elif self.path == "/api/estado":
            self._json(200, estado())
        else:
            self._json(404, {"erro": "não existe essa rota"})

    def do_POST(self):
        if not self._local():
            return
        if self.path == "/api/minerar":
            return self._json(200, minerar())
        if self.path == "/api/enviar":
            n = int(self.headers.get("Content-Length", 0))
            try:
                d = json.loads(self.rfile.read(n))
            except Exception:
                return self._json(400, {"erro": "não entendi o pedido."})
            return self._json(200, enviar(d.get("para"), d.get("valor"),
                                          d.get("taxa")))
        self._json(404, {"erro": "não existe essa rota"})

    def log_message(self, *a):
        pass


def main():
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else PORTA
    priv, pub, eu, nova = C.carrega_carteira()
    if nova:
        print("Criei uma carteira nova. Veja as doze palavras dela com")
        print("  python3 cadeia.py semente\n")
    C.carrega_cadeia()
    print("A tela do Tempest está no ar. Abra no navegador:\n")
    print("    http://127.0.0.1:%d\n" % porta)
    print("carteira:", eu)
    print("ctrl-c para desligar. Só esta máquina alcança esta tela.")
    ThreadingHTTPServer((ENDERECO, porta), Tela).serve_forever()


if __name__ == "__main__":
    main()
