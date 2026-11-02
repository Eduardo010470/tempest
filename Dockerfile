# O no do Tempest.
#
# Versao do Python escrita, nao adivinhada: builder que deduz linguagem
# erra, e quando erra o no nao sobe.
FROM python:3.11-slim

WORKDIR /tempest
COPY . .

# Nenhum pip. O Tempest nao tem dependencia alguma — a imagem base ja
# traz tudo o que ele usa. Se um dia aparecer um 'pip install' aqui, foi
# engano.
#
# PYTHONUNBUFFERED porque sem isso o print fica preso no buffer e os
# logs do provedor aparecem minutos depois, ou nunca.
ENV PYTHONUNBUFFERED=1

# A porta vem do ambiente (PORT). O no le ela sozinho.
CMD ["python3", "no.py", "servir"]
