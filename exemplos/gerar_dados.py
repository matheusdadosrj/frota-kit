"""Gera uma frota 100% fictícia, com os problemas que o kit precisa encontrar.

As fontes imitam o mundo real de propósito, cada uma num formato diferente:

    dados_exemplo/erp.sqlite                 cadastro de veículos e ordens de serviço (um "ERP")
    dados_exemplo/cartao_frota.csv           transações do cartão combustível (separador ; e vírgula decimal)
    dados_exemplo/viagens.csv                viagens do sistema de roteirização (Bases Norte e Centro)
    dados_exemplo/diario_base_sul.xlsx       diário de bordo da Base Sul: grade placa x dia com siglas
    dados_exemplo/decisoes.csv               decisões manuais registradas na conferência
    dados_exemplo/rastreador_a.csv           fornecedor A de rastreador (identifica pela placa)
    dados_exemplo/rastreador_b.xlsx          fornecedor B (identifica pelo apelido "Van 03 - ZZA1B23")
    dados_exemplo/conversa_whatsapp.txt      formulários de pagamento por PIX postados num grupo

Problemas plantados (o README mostra o kit encontrando cada um):
    registro em dobro, odômetro com dígito a mais, odômetro digitado errado, abastecimento fora do
    cartão, "tanque cheio" que não encheu (serrote), litros acima do tanque, motorista que gasta
    mais, posto caro, OS esquecida aberta, veículo parado há meses na oficina, veículo vendido que
    abasteceu, veículos ociosos, rastreador sem sinal, formulário reenviado, odômetro copiado,
    placa errada, pedido de PIX para veículo na oficina; no diário: placa com O no lugar de 0,
    placa com um caractere trocado, linha "RESERVA", sigla sem legenda, manutenção só no diário
    (sem OS), dias futuros preenchidos com 0 e coluna de total no meio da grade.

Uso:  python exemplos/gerar_dados.py   (ou: python -m frotakit exemplo)
"""
from __future__ import annotations

import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
SAIDA = RAIZ / "dados_exemplo"
FIM = datetime(2026, 11, 20)
DIAS = 120

MODELOS = {  # modelo: (grupo, combustível, tanque L, km/L típico, km por dia)
    "Hatch 1.0": ("carro", "gasolina", 50, 12.5, 140),
    "Furgão compacto": ("utilitario", "gasolina", 55, 10.0, 160),
    "Van média": ("van", "diesel", 80, 8.5, 180),
    "Caminhão 3/4": ("caminhao", "diesel", 150, 5.2, 200),
}
BASES = {"Base Norte": "Cidade Norte", "Base Sul": "Cidade Sul", "Base Centro": "Cidade Centro"}
POSTOS = {  # posto: (cidade, ágio sobre o preço da cidade)
    "Posto Alfa": ("Cidade Norte", 0.00), "Posto Beta": ("Cidade Norte", 0.01), "Posto Delta": ("Cidade Norte", 0.09),
    "Posto Gama": ("Cidade Sul", 0.00), "Posto Épsilon": ("Cidade Sul", 0.02),
    "Posto Zeta": ("Cidade Centro", 0.00), "Posto Eta": ("Cidade Centro", 0.015), "Posto Teta": ("Cidade Centro", 0.06),
}
PRECO = {"gasolina": 6.19, "diesel": 6.05}


def placa(i: int) -> str:
    """Placas fictícias no padrão Mercosul, todas começando com ZZ."""
    letras = "ABCDEFGHJKLMNPRSTUVWXY"
    return f"ZZ{letras[i // 10 % len(letras)]}{i % 10}{letras[(i * 7) % len(letras)]}{(i * 37) % 100:02d}"


def typo(placa_real: str) -> str:
    """Troca o último dígito: erro de digitação que gera uma placa que não existe no cadastro."""
    return placa_real[:-1] + str((int(placa_real[-1]) + 5) % 10)


def escrever_diario(V, viagens, parada, inicio, sul, casos, semente=7):
    """Diário de bordo da Base Sul como as bases fazem: uma aba por mês, título em cima, datas no
    cabeçalho, coluna de modelo e de total no meio, dias futuros já preenchidos com 0."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    rnd = random.Random(semente)
    rodou = {(v["placa"], v["data"]) for v in viagens}
    wb = Workbook()
    wb.remove(wb.active)
    ultimo_dia = (FIM - timedelta(days=1)).date()            # o diário é preenchido até ontem
    for ano, mes, nome in [(2026, 10, "OUT-26"), (2026, 11, "NOV-26")]:
        ws = wb.create_sheet(nome)
        ws["A1"] = f"DIÁRIO DE BORDO - BASE SUL - {nome}"
        ws["A1"].font = Font(bold=True)
        dias = pd.date_range(f"{ano}-{mes:02d}-01", periods=31 if mes == 10 else 30, freq="D")
        ws.append([])
        ws.append(["PLACA", "MODELO", "TOTAL ROTAS"] + [d.to_pydatetime() for d in dias])
        for col in range(4, 4 + len(dias)):
            ws.cell(row=3, column=col).number_format = "DD/MM"
        linhas = sorted(sul) + ["RESERVA"]
        for k in linhas:
            codigos = []
            for d in dias:
                dia = d.date()
                if dia > ultimo_dia:
                    codigos.append(0)
                    continue
                n = (dia - inicio.date()).days
                if k == "RESERVA":
                    codigos.append(1 if rnd.random() < 0.3 else None)
                elif (k, dia) in rodou:
                    codigos.append(rnd.choice([1, 1, 1, 2]))
                elif k in parada and parada[k][0] <= n < parada[k][1]:
                    if V[k]["status"] != "ATIVO":
                        codigos.append(None)              # devolvido: a linha fica em branco
                    elif k == casos["so_diario"] or k in OS_ABERTAS:
                        codigos.append("M")
                    else:
                        codigos.append("SR")               # parado sem rota
                elif d.weekday() == 6:
                    codigos.append("F")
                else:
                    codigos.append(None)
            if k == casos["sigla_nova"] and mes == 11:
                codigos[dias.get_loc(pd.Timestamp(ultimo_dia))] = "RIO"   # sigla que ninguém sabe o que é
            nome_placa = k
            if k == casos["digitada_O"]:
                nome_placa = k[:3] + "O" + k[4:]           # letra O no lugar do zero
            if k == casos["ligar"]:
                nome_placa = typo(k)
            if k == casos["sugerir"] and mes == 11:
                nome_placa = typo(k)
            total = sum(c for c in codigos if isinstance(c, int))
            ws.append([nome_placa, V[k]["modelo"] if k in V else "", total] + codigos)
    leg = wb.create_sheet("LEGENDA")
    for linha in [("SIGLA", "SIGNIFICADO"), ("1, 2, 3", "Nº de rotas"), ("M", "Manutenção"), ("F", "Folga"),
                  ("SR", "Sem rota"), ("SM", "Sem motorista")]:
        leg.append(linha)
    wb.save(SAIDA / "diario_base_sul.xlsx")


OS_ABERTAS: set = set()


def main(semente: int = 42):
    rnd = random.Random(semente)
    SAIDA.mkdir(exist_ok=True)
    inicio = FIM - timedelta(days=DIAS)

    # ------------------------------------------------------------------ frota
    distribuicao = ["Hatch 1.0"] * 18 + ["Furgão compacto"] * 20 + ["Van média"] * 16 + ["Caminhão 3/4"] * 6
    veiculos = []
    for i, modelo in enumerate(distribuicao):
        grupo, comb, tanque, kml, _ = MODELOS[modelo]
        veiculos.append({"placa": placa(i), "modelo": modelo, "grupo": grupo, "combustivel": comb, "tanque": tanque,
                         "kml": kml * rnd.gauss(1, 0.05), "base": list(BASES)[i % 3], "status": "ATIVO",
                         "dt_status": None, "motorista": f"Motorista {i % 45 + 1:02d}", "odo": rnd.randint(15_000, 160_000)})
    V = {v["placa"]: v for v in veiculos}
    p = [v["placa"] for v in veiculos]
    # casos plantados
    vendido, devolvido, vendido_rodou = p[57], p[58], p[59]
    V[vendido].update(status="VENDIDO", dt_status=FIM - timedelta(days=60))
    V[devolvido].update(status="DEVOLVIDO", dt_status=FIM - timedelta(days=30))
    V[vendido_rodou].update(status="VENDIDO", dt_status=FIM - timedelta(days=20))   # mas abasteceu depois
    ociosos = [p[50], p[51], p[52]]
    os_longa, os_esquecida, os_recentes = p[40], p[41], [p[42], p[43], p[44]]
    OS_ABERTAS.update([os_longa, os_esquecida, *os_recentes])
    duplicado, digito, digitado, fora_cartao, serrote, acima = p[3], p[5], p[6], p[9], p[8], p[10]
    gastao, economico = "Motorista 07", "Motorista 12"
    V[p[1]]["motorista"] = gastao                 # cada um dirige dois veículos de grupos diferentes
    V[p[22]]["motorista"] = gastao
    V[p[11]]["motorista"] = economico
    V[p[31]]["motorista"] = economico
    # a cada semana o veículo fica com o titular (60%) ou com outro motorista do quadro: é essa
    # rotação que permite separar o efeito do motorista do efeito do veículo
    quadro = [f"Motorista {n:02d}" for n in range(1, 52)]
    escala = {}

    # ------------------------------------------------------------------ simulação diária
    trans, viagens = [], []
    nivel = {k: v["tanque"] * rnd.uniform(0.5, 1) for k, v in V.items()}
    parada = {}                                   # placa -> (dia início, dia fim) sem rodar
    for k in ociosos:
        parada[k] = (DIAS - rnd.randint(12, 40), DIAS + 1)
    parada[os_longa] = (DIAS - 75, DIAS + 1)
    parada[os_esquecida] = (DIAS - 15, DIAS - 12)  # voltou a rodar, mas a OS ficou aberta
    so_diario, decisao_manut, sigla_nova = p[46], p[33], p[49]
    parada[so_diario] = (DIAS - 2, DIAS + 1)       # parou: o diário marca M, mas ninguém abriu OS
    parada[decisao_manut] = (DIAS - 3, DIAS + 1)   # batido; a gestão registra a decisão manual
    for k in os_recentes:
        parada[k] = (DIAS - rnd.randint(1, 4), DIAS + 1)
    for k in (vendido, devolvido):
        parada[k] = ((V[k]["dt_status"] - inicio).days - 3, DIAS + 1)
    pular_registro_feito, cheios_serrote = False, 0

    for d in range(DIAS):
        dia = inicio + timedelta(days=d)
        if dia.weekday() == 6:
            continue
        for k, v in V.items():
            if k in parada and parada[k][0] <= d < parada[k][1]:
                continue
            if k == vendido_rodou and d > (V[k]["dt_status"] - inicio).days + 1:
                continue
            if (k, d // 7) not in escala:
                escala[(k, d // 7)] = v["motorista"] if rnd.random() < 0.6 else rnd.choice(quadro)
            motorista = escala[(k, d // 7)]
            fator = 0.82 if motorista == gastao else 1.10 if motorista == economico else 1.0
            km = max(20, rnd.gauss(MODELOS[v["modelo"]][4], 30))
            gasto = km / (v["kml"] * fator * rnd.gauss(1, 0.04))
            v["odo"] += km
            nivel[k] = max(nivel[k] - gasto, 0.05 * v["tanque"])
            viagens.append({"placa": k, "data": dia.date(), "motorista": motorista, "km": round(km)})
            if nivel[k] > 0.35 * v["tanque"]:
                continue
            # ---- abastecimento
            cidade = BASES[v["base"]]
            postos = [n for n, (c, _) in POSTOS.items() if c == cidade]
            posto = "Posto Delta" if (motorista == gastao and rnd.random() < 0.7 and cidade == "Cidade Norte") else rnd.choice(postos)
            preco = PRECO[v["combustivel"]] * (1 + POSTOS[posto][1]) * rnd.gauss(1, 0.006) * (1 + 0.004 * (d // 30))
            cheio = rnd.random() < 0.85 or (k == serrote and cheios_serrote % 6 == 1)
            litros = (v["tanque"] - nivel[k]) * rnd.uniform(0.97, 1.0) if cheio else round(100 / preco, 2)
            if k == serrote and cheio:
                cheios_serrote += 1
                if cheios_serrote % 6 == 0:
                    litros *= 0.55                 # marcado como cheio, mas a bomba parou antes
            litros = round(min(litros, v["tanque"] - nivel[k]), 2)
            nivel[k] += litros
            hora = dia + timedelta(hours=rnd.randint(6, 19), minutes=rnd.randint(0, 59))
            odo = round(v["odo"])
            linha = {"Placa": k, "Data/Hora": hora.strftime("%d/%m/%Y %H:%M"), "Litros": litros,
                     "Valor Total": round(litros * preco, 2), "Hodometro": odo, "Tanque Cheio": "S" if cheio else "N",
                     "Produto": v["combustivel"].upper(), "Estabelecimento": posto, "Cidade": cidade, "Condutor": motorista}
            if rnd.random() < 0.01:
                linha["Hodometro"] = ""
            if k == fora_cartao and DIAS - 60 < d and not pular_registro_feito and cheio:
                pular_registro_feito = True         # abasteceu fora do cartão: o registro não existe
                continue
            trans.append(linha)
    # erros de registro plantados em posições fixas do histórico
    da_placa = lambda k: [t for t in trans if t["Placa"] == k]
    da_placa(digito)[-20]["Hodometro"] *= 10                     # dígito a mais
    da_placa(digitado)[-12]["Hodometro"] += 30_000               # erro de digitação
    for t in (da_placa(duplicado)[-5], da_placa(duplicado)[-15]):  # registro em dobro
        hora = datetime.strptime(t["Data/Hora"], "%d/%m/%Y %H:%M") + timedelta(minutes=4)
        trans.append({**t, "Data/Hora": hora.strftime("%d/%m/%Y %H:%M")})
    # litros acima do tanque (dois veículos abastecidos no mesmo cartão)
    t_acima = da_placa(acima)[-3]
    t_acima["Litros"] = round(t_acima["Litros"] + 40, 2)
    t_acima["Valor Total"] = round(t_acima["Valor Total"] + 40 * 6.2, 2)
    t_acima["Tanque Cheio"] = "N"
    # veículo vendido que abasteceu depois da baixa
    dia_v = V[vendido_rodou]["dt_status"] + timedelta(days=3, hours=10)
    trans.append({"Placa": vendido_rodou, "Data/Hora": dia_v.strftime("%d/%m/%Y %H:%M"), "Litros": 38.5,
                  "Valor Total": 238.32, "Hodometro": round(V[vendido_rodou]["odo"] + 150), "Tanque Cheio": "N",
                  "Produto": "GASOLINA", "Estabelecimento": "Posto Alfa", "Cidade": "Cidade Norte", "Condutor": "Motorista 30"})

    tr = pd.DataFrame(trans)
    for c in ("Litros", "Valor Total"):
        tr[c] = tr[c].map(lambda x: f"{x:.2f}".replace(".", ","))
    tr.to_csv(SAIDA / "cartao_frota.csv", sep=";", index=False, encoding="utf-8-sig")
    # a Base Sul não tem roteirizador: o uso dela vem do diário de bordo (grade placa x dia)
    sul = {k for k, v in V.items() if v["base"] == "Base Sul"}
    pd.DataFrame([v for v in viagens if v["placa"] not in sul]).to_csv(SAIDA / "viagens.csv", index=False)
    escrever_diario(V, viagens, parada, inicio, sul, {"so_diario": so_diario, "sigla_nova": sigla_nova,
                    "digitada_O": p[10], "ligar": p[13], "sugerir": p[16]})
    pd.DataFrame([
        {"placa": typo(p[13]), "acao": "ligar", "valor": p[13], "motivo": "placa digitada errada no diário de novembro",
         "quem": "Coordenação Base Sul", "data": "18/11/2026"},
        {"placa": "RESERVA", "acao": "ignorar", "valor": "", "motivo": "linha de veículo reserva, sem placa definida",
         "quem": "Coordenação Base Sul", "data": "18/11/2026"},
        {"placa": decisao_manut, "acao": "situacao", "valor": "Manutenção",
         "motivo": "colisão; aguardando vistoria da seguradora para abrir a OS", "quem": "Gestão de frota",
         "data": (FIM - timedelta(days=3)).strftime("%d/%m/%Y")},
    ]).to_csv(SAIDA / "decisoes.csv", sep=";", index=False, encoding="utf-8-sig")

    # ------------------------------------------------------------------ ERP (SQLite)
    oficinas = ["Oficina Mecânica Exemplo", "Centro Automotivo Modelo", "Retífica Fictícia"]
    ordens, n_os = [], 48000
    for k, v in V.items():
        for _ in range(rnd.randint(0, 3)):                    # histórico fechado
            ab = inicio + timedelta(days=rnd.randint(0, DIAS - 20))
            n_os += 1
            ordens.append((str(n_os), k, ab.strftime("%Y-%m-%d %H:%M"), (ab + timedelta(days=rnd.randint(1, 6))).strftime("%Y-%m-%d %H:%M"),
                           "FECHADA", rnd.choice(oficinas), rnd.choice(["Revisão preventiva", "Troca de pastilhas", "Pneu", "Suspensão"]),
                           round(rnd.uniform(250, 2500), 2)))
    for k, motivo, status in [(os_longa, "Motor - aguardando peça", "AGUARDANDO PECA"),
                              (os_esquecida, "Embreagem", "ABERTA")] + [(k, "Revisão preventiva", "EM ANDAMENTO") for k in os_recentes]:
        n_os += 1
        ab = inicio + timedelta(days=parada[k][0], hours=9)
        ordens.append((str(n_os), k, ab.strftime("%Y-%m-%d %H:%M"), None, status, rnd.choice(oficinas), motivo, None))
    arquivo = SAIDA / "erp.sqlite"
    arquivo.unlink(missing_ok=True)
    with sqlite3.connect(arquivo) as con:
        con.execute("CREATE TABLE cad_veiculo (PLACA_VEIC TEXT, DESC_MODELO TEXT, CATEGORIA TEXT, TP_COMBUST TEXT, "
                    "CAP_TANQUE REAL, FILIAL TEXT, SITUACAO TEXT, DT_SITUACAO TEXT)")
        con.executemany("INSERT INTO cad_veiculo VALUES (?,?,?,?,?,?,?,?)", [
            (k, v["modelo"], v["grupo"].upper(), v["combustivel"].upper(), v["tanque"], v["base"], v["status"],
             v["dt_status"].strftime("%Y-%m-%d") if v["dt_status"] else None) for k, v in V.items()])
        con.execute("CREATE TABLE ordem_servico (NR_OS TEXT, PLACA TEXT, DT_ABERTURA TEXT, DT_FECHAMENTO TEXT, "
                    "STATUS TEXT, FORNECEDOR TEXT, SERVICO TEXT, VL_TOTAL REAL)")
        con.executemany("INSERT INTO ordem_servico VALUES (?,?,?,?,?,?,?,?)", ordens)

    # ------------------------------------------------------------------ rastreadores
    coord = {"Cidade Norte": (-23.45, -46.60), "Cidade Sul": (-23.70, -46.65), "Cidade Centro": (-23.55, -46.63)}
    ultima_viagem = pd.DataFrame(viagens).groupby("placa")["data"].max()
    pos_a, pos_b = [], []
    for i, (k, v) in enumerate(V.items()):
        if v["status"] != "ATIVO" and k != vendido_rodou:
            continue
        lat, lon = coord[BASES[v["base"]]]
        ultimo = pd.Timestamp(ultima_viagem.get(k, inicio))
        for h in range(3):
            quando = ultimo + timedelta(hours=8 + 3 * h, minutes=rnd.randint(0, 59))
            if k in ociosos or k in (os_longa, so_diario, decisao_manut) or k in os_recentes:
                quando = FIM + timedelta(hours=7 + h)          # parado, mas o rastreador comunica
            if i == 2:
                quando = FIM - timedelta(days=6, hours=-h)      # rastreador sem sinal
            ponto = (round(lat + rnd.uniform(-.05, .05), 5), round(lon + rnd.uniform(-.05, .05), 5))
            ligada = not (k in ociosos or k in (os_longa, so_diario, decisao_manut) or k in os_recentes)
            if i % 3:
                pos_a.append({"placa": k, "data_hora": quando.strftime("%Y-%m-%d %H:%M:%S"), "lat": ponto[0], "lon": ponto[1],
                              "ignicao": int(ligada), "endereco": f"Rua Fictícia {rnd.randint(1, 999)}, {BASES[v['base']]}"})
            else:
                pos_b.append({"Veiculo": f"{v['modelo'].split()[0]} {i:02d} - {k[:3]}-{k[3:]}", "Ultima Comunicacao": quando.strftime("%d/%m/%Y %H:%M"),
                              "Latitude": ponto[0], "Longitude": ponto[1], "Motor": "Ligado" if ligada else "Desligado",
                              "Local": f"Av. Exemplo {rnd.randint(1, 3000)}, {BASES[v['base']]}"})
    pd.DataFrame(pos_a).to_csv(SAIDA / "rastreador_a.csv", index=False)
    pd.DataFrame(pos_b).to_excel(SAIDA / "rastreador_b.xlsx", index=False)

    # ------------------------------------------------------------------ WhatsApp (pedidos de PIX)
    pix = {"Posto Alfa": "00.000.001/0001-01", "Posto Gama": "00.000.002/0001-02", "Posto Zeta": "00.000.003/0001-03"}
    linhas, t = [], FIM - timedelta(days=7)

    def form(k, motorista, valor, km, posto="Posto Alfa", tem_pix=True):
        return "\n".join(["📋 FORMULÁRIO DE ABASTECIMENTO", f"PLACA: {k}", f"MOTORISTA: {motorista}",
                          f"VALOR: R$ {valor:.2f}".replace(".", ","), f"KM: {km:,}".replace(",", "."),
                          f"PIX DO POSTO: {pix[posto] if tem_pix else ''}", f"POSTO: {posto}"])

    def enviar(autor, texto, passo=None):
        nonlocal t
        t += passo or timedelta(minutes=rnd.randint(5, 50))
        linhas.append(f"{t:%d/%m/%Y %H:%M} - {autor}: {texto}")

    frota_pix = [k for k in p[12:22]]
    km_pix = {k: rnd.randint(30_000, 90_000) for k in frota_pix}
    for dia in range(6):
        t = FIM - timedelta(days=6 - dia) + timedelta(hours=7)
        for j, k in enumerate(frota_pix):
            if rnd.random() < 0.35:
                continue
            km_pix[k] += rnd.randint(120, 220)
            enviar(f"Supervisor {j % 3 + 1}", form(k, V[k]["motorista"], rnd.choice([100, 150, 200]), km_pix[k],
                                                  rnd.choice(list(pix))))
            if rnd.random() < 0.3:
                enviar("Financeiro", "Pago ✅")
        enviar("Supervisor 2", "Bom dia pessoal, lembrem de mandar a foto da nota.")
    a, b, c = frota_pix[0], frota_pix[1], frota_pix[2]
    enviar("Supervisor 1", form(a, V[a]["motorista"], 150, km_pix[a] + 180))
    enviar("Supervisor 1", form(a, V[a]["motorista"], 150, km_pix[a] + 180))                 # reenvio
    enviar("Supervisor 2", form(b, V[b]["motorista"], 100, km_pix[b]), timedelta(hours=20))   # KM copiado
    enviar("Supervisor 3", form(c[:5], V[c]["motorista"], 100, 51_200))                       # placa incompleta
    enviar("Supervisor 3", form(c, V[c]["motorista"], 200, km_pix[c] + 200, tem_pix=False))   # sem PIX
    enviar("Supervisor 1", form("ZZZ9Z99", "Motorista 44", 150, 77_000))                     # fora do cadastro
    enviar("Supervisor 2", form(os_longa, "Motorista 41", 200, 98_500))                        # veículo na oficina
    (SAIDA / "conversa_whatsapp.txt").write_text("\n".join(linhas) + "\n", encoding="utf-8")

    (SAIDA / "LEIA-ME.txt").write_text("Dados 100% fictícios gerados por exemplos/gerar_dados.py.\n", encoding="utf-8")
    print(f"Frota fictícia em {SAIDA}: {len(V)} veículos, {len(tr)} abastecimentos, {len(viagens)} viagens, "
          f"{len(ordens)} OS, {len(pos_a) + len(pos_b)} posições, {sum(1 for l in linhas if 'FORMULÁRIO' in l)} formulários")


if __name__ == "__main__":
    main()
