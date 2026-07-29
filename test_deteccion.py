import os
from deteccion import Detector, Lexico

CFG = dict(
    rafaga=True, simultaneas=True, tecla_pegada=True, prediccion=True,
    velocidad=True, repeticion=True, basura=True,
    sin_campo=True, held_threshold=3, burst_keys=5, burst_window=0.5,
    hold_ms=1100, cooldown=1.0,
    vel_keys=6, vel_window=0.18, rep_keys=7, rep_window=1.2, basura_min=5,
)

LX = Lexico.cargar(os.path.join(os.path.dirname(__file__), "es_50k.txt"))


def det(**over):
    cfg = dict(CFG, **over)
    return Detector(cfg, LX)


def feed_word(d, palabra, t0=0.0, dt=0.06, campo=True):
    motivo = None
    t = t0
    for i, ch in enumerate(palabra):
        motivo = motivo or d.feed(ch, 200 + i, "down", t, campo)
        d.feed(ch, 200 + i, "up", t + 0.02, campo)
        t += dt
    return motivo


def test_lexico_cargo():
    assert len(LX.words) > 1000, "el diccionario deberia haber cargado"
    assert LX.score("hola") > LX.score("xkqwz"), "palabra real > gibberish"


def test_gato_rafaga_gibberish():
    d = det()
    # pata paseando: teclas al azar, sin soltar bien, rapido
    motivo = None
    t = 0
    for i, sc in enumerate([30, 45, 21, 44, 46, 25]):
        motivo = motivo or d.feed("qwzxcv"[i], sc, "down", t)
        t += 0.05
    assert motivo, "mash rapido sin palabra deberia disparar"


def test_humano_palabra_rapida_no_dispara():
    # escribo "porque" rapidisimo -> es palabra real -> NO debe botar
    d = det()
    assert feed_word(d, "porque", dt=0.05) is None


def test_humano_frase_rapida_no_dispara():
    d = det()
    disparo = None
    t = 0
    for w in ["hola", "como", "estas", "amigo"]:
        disparo = disparo or feed_word(d, w, t0=t, dt=0.05)
        t += len(w) * 0.05 + 0.1
        d.feed("space", 57, "down", t); d.feed("space", 57, "up", t + 0.01)
        t += 0.1
    assert disparo is None, "escribir palabras reales rapido no debe botar"


def test_teclas_simultaneas():
    d = det()
    motivo = None
    for i, sc in enumerate([20, 21, 22]):
        motivo = motivo or d.feed("abc"[i], sc, "down", 5.0)  # 3 juntas sin soltar
    assert motivo == "teclas simultaneas"


def test_tecla_pegada():
    d = det()
    d.feed("k", 37, "down", 10.0)          # gato sentado en la K
    assert d.check_hold(10.5) is None       # aun no
    assert d.check_hold(11.2) == "tecla pegada"


def test_tecla_exenta_no_pega():
    d = det()
    d.feed("space", 57, "down", 10.0)       # mantener espacio es normal
    assert d.check_hold(12.0) is None


def test_sin_campo_mas_agresivo():
    # misma palabra real, pero sin campo de texto -> mas facil que dispare
    d = det()
    motivo = feed_word(d, "hola", dt=0.05, campo=False)
    assert motivo, "sin campo de texto debe ser mas agresivo"


def test_atajo_modificadores_no_dispara():
    # Ctrl+Shift+S: 2 modificadores + 1 tecla -> NO debe contar como simultaneas
    d = det()
    m = None
    m = m or d.feed("ctrl", 29, "down", 1.0)
    m = m or d.feed("shift", 42, "down", 1.05)
    m = m or d.feed("s", 31, "down", 1.1)
    assert m is None, "un atajo con modificadores no debe botar"


def test_gaming_simultaneas_no_dispara_en_pantalla_completa():
    # WASD sostenidas en un juego (pantalla completa) -> no debe botar
    d = det()
    m = None
    for i, k in enumerate("wasd"):
        m = m or d.feed(k, 40 + i, "down", 2.0, juego=True)
    assert m is None, "WASD en juego no debe botar"


def test_gaming_si_dispara_fuera_de_juego():
    # esas mismas teclas sostenidas en el escritorio (no juego) -> si es gato
    d = det()
    m = None
    for i, k in enumerate("wasd"):
        m = m or d.feed(k, 40 + i, "down", 3.0, juego=False)
    assert m, "varias teclas sostenidas fuera de un juego si debe botar"


def test_palabra_valida_baja_sospechas():
    # misma cantidad de teclas: basura dispara, palabra real no
    d1 = det(burst_keys=4)
    basura = feed_word(d1, "xkqz", dt=0.05)
    d2 = det(burst_keys=4)
    real = feed_word(d2, "hola", dt=0.05)
    assert basura, "basura deberia disparar"
    assert real is None, "una palabra valida debe bajar las sospechas"


def test_prefijo_valido_tolera_mas():
    # 'computa' es principio de 'computadora' -> no debe botar aunque sea largo
    d = det(burst_keys=4)
    assert feed_word(d, "computa", dt=0.04) is None


def test_freno_misma_tecla_repetida():
    # "aaaaaaa" antes NO se detectaba (contaba como una sola tecla distinta)
    d = det()
    motivo, t = None, 0.0
    for _ in range(9):
        motivo = motivo or d.feed("a", 30, "down", t)
        d.feed("a", 30, "up", t + 0.03)
        t += 0.12
    assert motivo == "misma tecla repetida", motivo


def test_freno_basura_lenta():
    # "sdrtg" escrito DESPACIO: la ventana de rafaga expira, pero es basura
    d = det()
    motivo, t = None, 0.0
    for i, ch in enumerate("sdrtg"):
        motivo = motivo or d.feed(ch, 40 + i, "down", t)
        d.feed(ch, 40 + i, "up", t + 0.05)
        t += 0.9          # lentisimo, una tecla por segundo casi
    assert motivo == "texto sin sentido", motivo


def test_freno_velocidad_imposible():
    # 5 teclas en 200ms = mas rapido que cualquier humano
    d = det()
    motivo, t = None, 0.0
    for i, ch in enumerate("qwerty"):       # se sueltan, para aislar velocidad
        motivo = motivo or d.feed(ch, 50 + i, "down", t)
        d.feed(ch, 50 + i, "up", t + 0.005)
        t += 0.025                          # 40 teclas/seg
    assert motivo == "tecleo imposible de rapido", motivo


def test_frenos_no_molestan_al_humano():
    # escribir despacio y bien no debe disparar ningun freno
    d = det()
    motivo, t = None, 0.0
    for palabra in ["hola", "como", "estas", "todo", "bien"]:
        for i, ch in enumerate(palabra):
            motivo = motivo or d.feed(ch, 60 + i, "down", t)
            d.feed(ch, 60 + i, "up", t + 0.04)
            t += 0.15
        motivo = motivo or d.feed("space", 57, "down", t)
        d.feed("space", 57, "up", t + 0.03)
        t += 0.2
    assert motivo is None, motivo


def test_doble_letra_normal_no_dispara():
    # "aa" de 'llamar', 'ee' de 'leer'... repetir 2-3 veces es normal
    d = det()
    motivo, t = None, 0.0
    for ch in "ll":
        motivo = motivo or d.feed(ch, 38, "down", t)
        d.feed(ch, 38, "up", t + 0.04)
        t += 0.14
    assert motivo is None, motivo


if __name__ == "__main__":
    for name in [n for n in dir() if n.startswith("test_")]:
        globals()[name]()
        print("OK", name)
    print("todos los tests pasaron")
