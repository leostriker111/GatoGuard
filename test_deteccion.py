import os
from deteccion import Detector, Lexico

CFG = dict(
    rafaga=True, simultaneas=True, tecla_pegada=True, prediccion=True,
    sin_campo=True, held_threshold=3, burst_keys=5, burst_window=0.5,
    hold_ms=1100, cooldown=1.0,
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


if __name__ == "__main__":
    for name in [n for n in dir() if n.startswith("test_")]:
        globals()[name]()
        print("OK", name)
    print("todos los tests pasaron")
