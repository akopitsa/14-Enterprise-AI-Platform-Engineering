"""Вправа 1: архітектурна діаграма telco-platform-lite.
Одна модель розкладки → два артефакти: diagram.drawio (редагується в draw.io) і diagram.svg → diagram.png.
Запуск: python homework/diagram/build_diagram.py && rsvg-convert -z 1.5 -b white homework/diagram/diagram.svg -o diagram.png"""
from html import escape
from pathlib import Path

OUT = Path(__file__).resolve().parent
W, H = 1720, 1090
FONT = "Noto Sans, Liberation Sans, Arial, sans-serif"

BLUE, RED, PURPLE, GREY = "#1d4ed8", "#dc2626", "#7c3aed", "#475569"
LANE = {  # рівень: (заливка доріжки, обведення)
    "platform": ("#e0f2fe", "#0369a1"),
    "agent": ("#fef3c7", "#b45309"),
    "llm": ("#dcfce7", "#15803d"),
    "ml": ("#fce7f3", "#be185d"),
}

# ── вузли: id, вид, x, y, w, h, рядки тексту (перший — жирний), заливка, обведення
N = {}


def node(i, kind, x, y, w, h, lines, fill="#ffffff", stroke=GREY, **kw):
    N[i] = dict(id=i, kind=kind, x=x, y=y, w=w, h=h, lines=lines, fill=fill, stroke=stroke, **kw)


# Зони
node("inet", "zone", 20, 240, 320, 300, ["ІНТЕРНЕТ — недовірена зона"], "#f1f5f9", "#94a3b8")
node("cp", "zone", 380, 60, 1310, 150, ["CONTROL PLANE — рідкісні зміни лише через PR, кожна в аудиті"], "#f5f3ff", PURPLE)
node("dp", "zone", 380, 240, 1020, 815, ["DATA PLANE — шлях кожного запиту"], "#f8fafc", "#0284c7")
node("ext", "zone", 1440, 525, 250, 330, ["ЗОВНІШНІ ІНСТРУМЕНТИ (MCP)"], "#fff7ed", "#ea580c")

# Доріжки чотирьох рівнів
for key, y, h, title in [("platform", 275, 240, "4 · ПЛАТФОРМА"), ("agent", 525, 160, "3 · АГЕНТ"),
                         ("llm", 695, 150, "2 · LLM"), ("ml", 855, 185, "1 · ML")]:
    node("lane_" + key, "lane", 395, y, 990, h, [title], *LANE[key])

# Клієнт
node("client", "box", 45, 325, 270, 96, ["Клієнт", "менеджер утримання в CRM UI", "орендар telco-crm", "HTTPS + Bearer JWT"],
     "#ffffff", "#334155")

# Control plane
node("idp", "box", 400, 100, 280, 92, ["IdP (у демо — security.py)", "видає JWT RS256:", "sub, tenant_id, role"], stroke=PURPLE)
node("git", "box", 700, 100, 320, 92, ["Git: політика як код", "rbac.yaml · idp.yaml · config.py", "(MAX_AUTO_DISCOUNT) → PR-рев'ю"],
     stroke=PURPLE)
node("cicd", "box", 1040, 100, 300, 92, ["IDP + CI/CD", "маніфест → idp_validate.py", "→ Terraform + Helm"], stroke=PURPLE)
node("reg", "box", 1360, 100, 310, 92, ["Model registry + картка моделі", "CI-gate: AUC ≥ 0.75,", "інакше шлюз не стартує"],
     stroke=PURPLE)

# Рівень 4: платформа — шлюз як конвеєр
P = LANE["platform"][1]
node("gw", "group", 460, 300, 915, 122, ["API-шлюз (gateway.py) — один middleware, кроки по черзі"], "#ffffff", P)
node("s1", "step", 475, 337, 165, 72, ["① Автентифікація", "JWT RS256", "→ 401"], "#eff6ff", BLUE)
node("s2", "step", 655, 337, 165, 72, ["② Перевірка прав", "RBAC scope", "→ 403"], "#eff6ff", BLUE)
node("s3", "step", 835, 337, 165, 72, ["Rate limit", "token bucket", "на орендаря → 429"], "#ffffff", P)
node("s4", "step", 1015, 337, 165, 72, ["Маршрутизація", "до сервісу; tenant", "лише з JWT"], "#eff6ff", BLUE)
node("s5", "step", 1195, 337, 170, 72, ["④ Облік + аудит", "request_id, cost_usd,", "decision, хеш промпту"], "#eff6ff", BLUE)
node("appr", "box", 475, 437, 205, 68, ["Черга схвалень", "human-in-the-loop", "(лише admin)"], stroke=P)
node("cost", "cyl", 1040, 432, 162, 76, ["$ Тут рахуються", "витрати: cost.py", "токени→USD, бюджет"],
     "#dcfce7", "#15803d")
node("audit", "cyl", 1212, 432, 163, 76, ["⑤ Сховище аудиту", "append-only: SQLite", "→ ClickHouse/WORM"], "#fef9c3", "#a16207")

# Рівень 3: агент
A = LANE["agent"][1]
node("ag", "group", 460, 548, 915, 127, ["③ Сервіс: агент утримання (agent.py)"], "#ffffff", A)
node("orch", "step", 475, 588, 170, 72, ["Оркестратор", "predict → retrieve", "→ explain"], stroke=A)
node("draft", "step", 665, 588, 165, 72, ["draft_offer", "виклик інструменту", "через MCP"], stroke=A)
node("guard", "step", 850, 588, 200, 72, ["guardrail_check", "знижка > MAX_AUTO_", "DISCOUNT → схвалення"], "#fff1f2", RED)
node("send", "step", 1070, 588, 290, 72, ["send_offer  /  human_approval", "status: offer_sent", "або pending_approval"], stroke=A)

# Рівень 2: LLM
L = LANE["llm"][1]
node("rag", "box", 475, 735, 260, 80, ["RAG: колекція орендаря", "векторна БД", "(у демо — пошук за тегами)"], stroke=L)
node("llm", "box", 760, 735, 300, 80, ["explainer-llm", "vLLM + AWQ (у демо — stub", "або OpenAI-сумісний API)"], stroke=L)
node("faith", "box", 1085, 735, 280, 80, ["Перевірка faithfulness", "RAGAS (у демо — лексичний", "проксі) → low_confidence"], stroke=L)

# Рівень 1: ML
M = LANE["ml"][1]
node("churn", "box", 475, 900, 260, 80, ["churn-predictor", "sklearn; дані лише", "свого орендаря"], stroke=M)
node("card", "box", 760, 900, 300, 80, ["Картка моделі", "artifacts/model_card.yaml", "stage, AUC, обмеження"], stroke=M)
node("feat", "box", 1085, 900, 280, 80, ["Дані / ознаки орендаря", "telco-crm · telco-b2b ·", "telco-trial (ізольовані)"], stroke=M)

# Зовнішні інструменти
node("offers", "box", 1460, 700, 210, 74, ["Каталог пропозицій", "offer_catalog.suggest"], stroke="#ea580c")
node("crm", "box", 1460, 570, 210, 74, ["CRM оператора", "надсилання пропозиції"], stroke="#ea580c")

# Легенда
node("legend", "legend", 20, 575, 320, 300, ["Легенда"], "#ffffff", "#94a3b8")

# Межі довіри: (id, x1, y1, x2, y2, підпис, позиція підпису)
BOUNDS = [
    ("b1", 355, 60, 355, 1070, "A · Інтернет → шлюз", (226, 558)),
    ("b2", 365, 225, 1700, 225, "B · Control → data plane (лише читання)", (780, 213)),
    ("b3", 1418, 520, 1418, 860, "C · Агент → зовнішні інструменти", (1405, 868)),
]

# ── ребра: (від, сторона, до, сторона, вид, підпис, проміжні точки)
E = [  # сторона: L/R/T/B або (fx, fy) — точка на контурі; 8-й елемент — позиція підпису
    ("client", "R", "s1", "L", "path", "", []),
    ("s1", "R", "s2", "L", "path", "", []),
    ("s2", "R", "s3", "L", "path", "", []),
    ("s3", "R", "s4", "L", "path", "", []),
    ("s4", (0.06, 1), "send", "T", "path", "до сервісу", [(1025, 560), (1215, 560)], (1120, 560)),
    ("s4", "R", "s5", "L", "path", "", []),
    ("s5", (0.57, 1), "audit", "T", "path", "", []),
    ("s5", (0.15, 1), "cost", "T", "data", "", [(1220, 421), (1121, 421)]),
    ("orch", "R", "draft", "L", "flow", "", []),
    ("draft", "R", "guard", "L", "flow", "", []),
    ("guard", "R", "send", "L", "flow", "", []),
    ("guard", "T", "appr", "B", "flow", "> ліміту → pending", [(950, 528), (577, 528)], (790, 528)),
    ("orch", "B", "rag", (0.327, 0), "flow", "retrieve", []),
    ("rag", "R", "llm", "L", "flow", "", []),
    ("llm", "R", "faith", "L", "flow", "", []),
    ("orch", "L", "churn", "L", "flow", "predict", [(455, 624), (455, 940)], (455, 850)),
    ("churn", "R", "card", "L", "flow", "", []),
    ("feat", "B", "churn", "B", "flow", "ознаки", [(1225, 1012), (605, 1012)]),
    ("draft", "B", "offers", "L", "ext", "MCP call_tool", [(747, 690), (1430, 690), (1430, 737)], (1090, 690)),
    ("send", "R", "crm", "L", "ext", "", [(1400, 624), (1400, 607)]),
    ("idp", (0.5607, 1), "s1", "T", "ctrl", "публічний ключ", []),
    ("git", (0.1156, 1), "s2", "T", "ctrl", "rbac.yaml", []),
    ("cicd", (0.5, 1), "dp", (0.7941, 0), "ctrl", "деплой", [], (1190, 213)),
]
EDGE_STYLE = {  # колір, товщина, штрих
    "path": (BLUE, 3.0, None), "flow": (GREY, 1.6, None), "data": ("#15803d", 1.6, "5 3"),
    "ext": ("#ea580c", 1.8, None), "ctrl": (PURPLE, 1.6, "2 4"),
}
SIDE = {"L": (0, 0.5), "R": (1, 0.5), "T": (0.5, 0), "B": (0.5, 1)}


def port(n, side):
    fx, fy = SIDE[side] if isinstance(side, str) else side
    return n["x"] + fx * n["w"], n["y"] + fy * n["h"]


# ═════════════════════════════════ SVG ═════════════════════════════════
def svg_text(x, y, lines, size=12.5, anchor="middle", bold_first=True, color="#0f172a", lh=16):
    out = []
    for k, line in enumerate(lines):
        weight = "700" if (k == 0 and bold_first) else "400"
        out.append(f'<text x="{x}" y="{y + k * lh}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" '
                   f'fill="{color}">{escape(line)}</text>')
    return "\n".join(out)


def svg_node(n):
    x, y, w, h, k = n["x"], n["y"], n["w"], n["h"], n["kind"]
    if k == "zone":
        dash = ' stroke-dasharray="8 5"' if n["id"] in ("inet", "ext") else ""
        right = n["id"] == "dp"
        return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{n["fill"]}" stroke="{n["stroke"]}" '
                f'stroke-width="2"{dash}/>' + svg_text(x + w - 14 if right else x + 14, y + 22, n["lines"], 13.5,
                                                       "end" if right else "start", color=n["stroke"]))
    if k == "lane":
        cy = y + h - 75 if n["id"] == "lane_platform" else y + h / 2   # нижче за лінію клієнт → шлюз
        return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{n["fill"]}" stroke="{n["stroke"]}" '
                f'stroke-width="1.2" stroke-opacity="0.5"/>'
                f'<text x="{x + 12}" y="{cy}" font-size="12" font-weight="800" fill="{n["stroke"]}" '
                f'text-anchor="middle" transform="rotate(-90 {x + 12} {cy})" dy="4" letter-spacing="0.5">'
                f'{escape(n["lines"][0])}</text>')
    if k == "group":
        return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{n["fill"]}" fill-opacity="0.7" '
                f'stroke="{n["stroke"]}" stroke-width="1.6"/>' + (svg_text(x + w - 14, y + 22, n["lines"], 13, "end", color=n["stroke"])
                                                       if n["id"] == "gw" else svg_text(x + 14, y + 22, n["lines"], 13, "start", color=n["stroke"])))
    if k == "cyl":
        ry = 8
        body = (f'<path d="M{x},{y + ry} L{x},{y + h - ry} A{w / 2},{ry} 0 0 0 {x + w},{y + h - ry} L{x + w},{y + ry}" '
                f'fill="{n["fill"]}" stroke="{n["stroke"]}" stroke-width="2"/>'
                f'<ellipse cx="{x + w / 2}" cy="{y + ry}" rx="{w / 2}" ry="{ry}" fill="{n["fill"]}" stroke="{n["stroke"]}" stroke-width="2"/>')
        return body + svg_text(x + w / 2, y + 33, n["lines"], 12, lh=15)
    if k == "legend":
        rows = [("path", "шлях запиту ①→⑤ (клієнт → шлюз →\nперевірка прав → сервіс → аудит)"),
                ("flow", "внутрішній виклик"), ("ext", "виклик зовнішнього інструменту"),
                ("data", "запис витрат"), ("ctrl", "конфігурація з control plane")]
        s = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="#fff" stroke="{n["stroke"]}"/>',
             svg_text(x + 14, y + 24, ["Легенда"], 13.5, "start")]
        yy = y + 52
        for kind, label in rows:
            c, sw, dash = EDGE_STYLE[kind]
            d = f' stroke-dasharray="{dash}"' if dash else ""
            s.append(f'<line x1="{x + 14}" y1="{yy - 4}" x2="{x + 58}" y2="{yy - 4}" stroke="{c}" stroke-width="{sw}"{d} '
                     f'marker-end="url(#m_{kind})"/>')
            s.append(svg_text(x + 70, yy, label.split("\n"), 12, "start", bold_first=False))
            yy += 20 + 16 * label.count("\n") + 8
        s.append(f'<line x1="{x + 14}" y1="{yy - 4}" x2="{x + 58}" y2="{yy - 4}" stroke="{RED}" stroke-width="2.5" stroke-dasharray="9 5"/>')
        s.append(svg_text(x + 70, yy, ["межа довіри A, B, C"], 12, "start", bold_first=False))
        yy += 28
        s.append(f'<rect x="{x + 14}" y="{yy - 13}" width="44" height="18" rx="4" fill="#eff6ff" stroke="{BLUE}"/>')
        s.append(svg_text(x + 70, yy, ["крок шлюзу на шляху запиту"], 12, "start", bold_first=False))
        yy += 26
        s.append(svg_text(x + 14, yy, ["Чотири рівні: ML → LLM → агент → платформа"], 12, "start", bold_first=True))
        xx = x + 14
        for key, label in [("ml", "ML"), ("llm", "LLM"), ("agent", "Агент"), ("platform", "Платформа")]:
            f, st = LANE[key]
            bw = 30 + 8 * len(label)
            s.append(f'<rect x="{xx}" y="{yy + 10}" width="{bw}" height="22" rx="5" fill="{f}" stroke="{st}"/>')
            s.append(f'<text x="{xx + bw / 2}" y="{yy + 25}" font-size="11.5" text-anchor="middle" fill="{st}" font-weight="700">{label}</text>')
            xx += bw + 6
        return "\n".join(s)
    # box / step
    rx = 8 if k == "step" else 10
    s = (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{n["fill"]}" stroke="{n["stroke"]}" '
         f'stroke-width="{2.2 if n["stroke"] in (BLUE, RED) else 1.6}"/>')
    lh = 15.5
    top = y + h / 2 - (len(n["lines"]) - 1) * lh / 2 + 4.5
    return s + svg_text(x + w / 2, top, n["lines"], 12.5 if k == "step" else 12.5, lh=lh)


def svg_edge(e):
    a, sa, b, sb, kind, label, pts, *lp = e
    c, sw, dash = EDGE_STYLE[kind]
    p = [port(N[a], sa), *pts, port(N[b], sb)]
    d = f' stroke-dasharray="{dash}"' if dash else ""
    s = (f'<polyline points="{" ".join(f"{x},{y}" for x, y in p)}" fill="none" stroke="{c}" stroke-width="{sw}"{d} '
         f'stroke-linejoin="round" marker-end="url(#m_{kind})"/>')
    if label:
        seg = max(zip(p, p[1:]), key=lambda q: abs(q[0][0] - q[1][0]) + abs(q[0][1] - q[1][1]))
        mx, my = lp[0] if lp else ((seg[0][0] + seg[1][0]) / 2, (seg[0][1] + seg[1][1]) / 2)
        tw = 7.2 * len(label) + 10
        s += (f'<rect x="{mx - tw / 2}" y="{my - 10}" width="{tw}" height="19" rx="4" fill="#fff" stroke="{c}" stroke-width="0.8"/>'
              f'<text x="{mx}" y="{my + 4}" font-size="11.5" font-weight="{700 if kind == "path" else 400}" '
              f'text-anchor="middle" fill="{c}">{escape(label)}</text>')
    return s


def svg_bound(b):
    _, x1, y1, x2, y2, label, (lx, ly) = b
    tw = 7.3 * len(label) + 16
    if lx + tw > W - 10:
        lx = W - 10 - tw
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{RED}" stroke-width="2.5" stroke-dasharray="10 6"/>'
            f'<rect x="{lx}" y="{ly - 13}" width="{tw}" height="22" rx="11" fill="{RED}"/>'
            f'<text x="{lx + tw / 2}" y="{ly + 3}" font-size="12" font-weight="700" fill="#fff" text-anchor="middle">{escape(label)}</text>')


def build_svg():
    markers = "".join(
        f'<marker id="m_{k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="{6 if k == "path" else 7}" '
        f'markerHeight="{6 if k == "path" else 7}" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>'
        for k, (c, _, _) in EDGE_STYLE.items())
    order = ["zone", "lane", "group", "box", "step", "cyl", "legend"]
    nodes = sorted(N.values(), key=lambda n: order.index(n["kind"]))
    body = [svg_text(20, 36, ["telco-platform-lite — AI-платформа утримання клієнтів: 4 рівні, шлях запиту, межі довіри"], 19, "start")]
    body += [svg_node(n) for n in nodes if n["kind"] in ("zone", "lane", "group")]
    body += [svg_bound(b) for b in BOUNDS]
    body += [svg_edge(e) for e in E]
    body += [svg_node(n) for n in nodes if n["kind"] not in ("zone", "lane", "group")]
    # повторно — підписи меж поверх усього
    body += [svg_bound(b) for b in BOUNDS]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
            f'font-family="{FONT}"><defs>{markers}</defs><rect width="{W}" height="{H}" fill="#fff"/>\n'
            + "\n".join(body) + "\n</svg>\n")


# ═════════════════════════════════ draw.io ═════════════════════════════════
def drawio_label(lines):
    head, rest = lines[0], lines[1:]
    return escape("<b>" + escape(head) + "</b>" + "".join("<br>" + escape(r) for r in rest), quote=True)


def build_drawio():
    cells, nid = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>'], 0

    def add(value, style, x, y, w, h):
        nonlocal nid
        nid += 1
        cells.append(f'<mxCell id="v{nid}" value="{value}" style="{style}" vertex="1" parent="1">'
                     f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
        return f"v{nid}"

    add(escape("<b>telco-platform-lite — AI-платформа утримання клієнтів: 4 рівні, шлях запиту, межі довіри</b>", quote=True),
        "text;html=1;fontSize=19;align=left;verticalAlign=middle;", 20, 18, 1100, 30)
    ids = {}
    order = ["zone", "lane", "group", "legend", "box", "step", "cyl"]
    for n in sorted(N.values(), key=lambda n: order.index(n["kind"])):
        k, f, st = n["kind"], n["fill"], n["stroke"]
        if k == "zone":
            dash = "dashed=1;" if n["id"] in ("inet", "ext") else ""
            align = "align=right;spacingRight=12;" if n["id"] == "dp" else "align=left;spacingLeft=12;"
            style = (f"rounded=1;arcSize=3;whiteSpace=wrap;html=1;fillColor={f};strokeColor={st};strokeWidth=2;{dash}"
                     f"verticalAlign=top;{align}fontSize=13;fontColor={st};")
        elif k == "lane":
            style = (f"rounded=1;arcSize=3;whiteSpace=wrap;html=1;fillColor={f};strokeColor={st};opacity=80;"
                     f"horizontal=0;verticalAlign=top;align=center;fontSize=12;fontStyle=1;fontColor={st};spacingTop=2;")
        elif k == "group":
            align = "align=right;spacingRight=12;" if n["id"] == "gw" else "align=left;spacingLeft=12;"
            style = (f"rounded=1;arcSize=6;whiteSpace=wrap;html=1;fillColor={f};strokeColor={st};strokeWidth=1.6;"
                     f"verticalAlign=top;{align}fontSize=13;fontColor={st};")
        elif k == "cyl":
            style = (f"shape=cylinder3;boundedLbl=1;size=8;whiteSpace=wrap;html=1;fillColor={f};strokeColor={st};"
                     f"strokeWidth=2;fontSize=12;")
        elif k == "legend":
            legend = ("<b>Легенда</b><br>"
                      f"<font color='{BLUE}'><b>━━▶</b></font> шлях запиту ①→⑤<br>"
                      f"<font color='{GREY}'>──▶</font> внутрішній виклик<br>"
                      f"<font color='#ea580c'>──▶</font> виклик зовнішнього інструменту<br>"
                      f"<font color='#15803d'>- - ▶</font> запис витрат<br>"
                      f"<font color='{PURPLE}'>··▶</font> конфігурація з control plane<br>"
                      f"<font color='{RED}'><b>— —</b></font> межа довіри A, B, C<br><br>"
                      "<b>Чотири рівні:</b> ML → LLM → агент → платформа")
            add(escape(legend, quote=True), f"rounded=1;whiteSpace=wrap;html=1;fillColor=#ffffff;strokeColor={st};"
                f"align=left;verticalAlign=top;spacing=12;fontSize=12;", n["x"], n["y"], n["w"], n["h"])
            continue
        else:
            sw = 2.2 if st in (BLUE, RED) else 1.6
            style = f"rounded=1;arcSize=10;whiteSpace=wrap;html=1;fillColor={f};strokeColor={st};strokeWidth={sw};fontSize=12;"
        value = escape(escape(n["lines"][0]), quote=True) if k in ("zone", "lane", "group") else drawio_label(n["lines"])
        if k in ("zone", "group"):
            value = escape("<b>" + escape(n["lines"][0]) + "</b>", quote=True)
        ids[n["id"]] = add(value, style, n["x"], n["y"], n["w"], n["h"])

    for _, x1, y1, x2, y2, label, (lx, ly) in BOUNDS:
        nid += 1
        cells.append(f'<mxCell id="b{nid}" value="" style="endArrow=none;html=1;strokeColor={RED};strokeWidth=2.5;dashed=1;'
                     f'dashPattern=10 6;" edge="1" parent="1"><mxGeometry relative="1" as="geometry">'
                     f'<mxPoint x="{x1}" y="{y1}" as="sourcePoint"/><mxPoint x="{x2}" y="{y2}" as="targetPoint"/>'
                     f'</mxGeometry></mxCell>')
        tw = 7.3 * len(label) + 16
        lx = min(lx, W - 10 - tw)
        add(escape("<b>" + escape(label) + "</b>", quote=True),
            f"rounded=1;arcSize=50;html=1;fillColor={RED};strokeColor=none;fontColor=#ffffff;fontSize=12;",
            lx, ly - 13, tw, 22)

    for a, sa, b, sb, kind, label, pts, *_ in E:
        c, sw, dash = EDGE_STYLE[kind]
        ex, ey = SIDE[sa] if isinstance(sa, str) else sa
        nx, ny = SIDE[sb] if isinstance(sb, str) else sb
        style = (f"edgeStyle=none;html=1;endArrow=block;endFill=1;strokeColor={c};strokeWidth={sw};"
                 f"exitX={ex};exitY={ey};exitDx=0;exitDy=0;entryX={nx};entryY={ny};entryDx=0;entryDy=0;"
                 f"fontSize=11;fontColor={c};labelBackgroundColor=#ffffff;"
                 + (f"dashed=1;dashPattern={dash};" if dash else "") + ("fontStyle=1;" if kind == "path" else ""))
        geo = "".join(f'<mxPoint x="{x}" y="{y}"/>' for x, y in pts)
        geo = f'<Array as="points">{geo}</Array>' if pts else ""
        nid += 1
        cells.append(f'<mxCell id="e{nid}" value="{escape(label, quote=True)}" style="{style}" edge="1" parent="1" '
                     f'source="{ids[a]}" target="{ids[b]}"><mxGeometry relative="1" as="geometry">{geo}</mxGeometry></mxCell>')

    return ('<mxfile host="build_diagram.py"><diagram id="arch" name="Архітектура">'
            f'<mxGraphModel dx="{W}" dy="{H}" grid="1" gridSize="10" guides="1" page="1" pageWidth="{W}" pageHeight="{H}" '
            f'math="0" shadow="0"><root>{"".join(cells)}</root></mxGraphModel></diagram></mxfile>\n')


if __name__ == "__main__":
    (OUT / "diagram.svg").write_text(build_svg(), encoding="utf-8")
    (OUT / "diagram.drawio").write_text(build_drawio(), encoding="utf-8")
    print("written:", OUT / "diagram.svg", OUT / "diagram.drawio")
