import math
import os

VOCALES = set("aeiouáéíóúü")
LETRAS = set("abcdefghijklmnopqrstuvwxyzñáéíóúü")
SEPARADORES = {"space", "enter", "tab", "esc"}

# teclas que un humano SI mantiene un rato -> no cuentan como "tecla pegada"
EXENTAS_HOLD = {
    "space", "backspace", "enter", "tab", "delete", "up", "down", "left",
    "right", "page up", "page down", "shift", "ctrl", "alt", "left shift",
    "right shift", "left ctrl", "right ctrl", "left alt", "right alt",
    "left windows", "right windows",
}

MODIFICADORES = {
    "shift", "ctrl", "alt", "left shift", "right shift", "left ctrl",
    "right ctrl", "left alt", "right alt", "left windows", "right windows",
    "caps lock", "windows",
}

# teclas tipicas de videojuego: si TODO lo presionado cae aqui (y hay pantalla
# completa) asumimos que estas jugando, no un gato
GAMING = {
    "w", "a", "s", "d", "up", "down", "left", "right", "space", "shift",
    "ctrl", "alt", "e", "q", "r", "f", "c", "v", "tab", "1", "2", "3", "4", "5",
}

SCORE_THRESH = 0.5


class Lexico:
    """Diccionario de frecuencias del espanol para juzgar si algo es texto real."""

    def __init__(self):
        self.words = {}
        self.prefixes = set()
        self.maxlog = 1.0

    @classmethod
    def cargar(cls, paths, limite=30000):
        lx = cls()
        if isinstance(paths, str):
            paths = [paths]
        for path in paths:
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i >= limite:
                        break
                    parts = line.split()
                    if len(parts) != 2:
                        continue
                    w, fr = parts[0].lower(), int(parts[1])
                    if fr > lx.words.get(w, 0):
                        lx.words[w] = fr
                    for k in range(1, len(w) + 1):
                        lx.prefixes.add(w[:k])
        if lx.words:
            lx.maxlog = math.log(max(lx.words.values()))
        return lx

    def _edits1(self, w):
        splits = [(w[:i], w[i:]) for i in range(len(w) + 1)]
        borra = [a + b[1:] for a, b in splits if b]
        trans = [a + b[1] + b[0] + b[2:] for a, b in splits if len(b) > 1]
        reemp = [a + c + b[1:] for a, b in splits if b for c in LETRAS]
        inser = [a + c + b for a, b in splits for c in LETRAS]
        return set(borra + trans + reemp + inser)

    def _heuristica(self, t):
        if len(t) < 2:
            return 0.7
        v = sum(c in VOCALES for c in t) / len(t)
        run = maxrun = 0
        for c in t:
            run = 0 if c in VOCALES else run + 1
            maxrun = max(maxrun, run)
        base = 0.6 if 0.2 <= v <= 0.65 else 0.3
        if maxrun >= 4:
            base -= 0.3
        return max(0.0, min(1.0, base))

    def score(self, token):
        """0..1: que tan probable es que 'token' sea una palabra real que alguien teclea."""
        t = token.lower()
        if not t:
            return 1.0
        if t in self.words:
            return 0.6 + 0.4 * (math.log(self.words[t]) / self.maxlog)
        if t in self.prefixes:
            return 0.8
        for e in self._edits1(t):
            if e in self.words or e in self.prefixes:
                return 0.6
        return self._heuristica(t)


class Detector:
    def __init__(self, config, lexico):
        self.cfg = config
        self.lx = lexico
        self.held = {}        # scan_code -> (name, down_time)
        self.recent = {}      # scan_code -> (nombre, time) del ultimo down
        self.token = ""       # palabra que se esta escribiendo
        self.downs = []       # tiempos de los ultimos keydown (velocidad)
        self.rep_sc = None    # tecla que se esta repitiendo
        self.rep_n = 0
        self.rep_t0 = 0.0

    def reset_estado(self):
        self.held.clear()
        self.recent.clear()
        self.token = ""
        self.downs.clear()
        self.rep_sc = None
        self.rep_n = 0

    def _actualiza_token(self, name):
        # los digitos tambien cuentan: 'rz555' en Blender es un desastre, y si
        # se borraba el token con cada numero nunca se llegaba a juzgar
        if len(name) == 1 and (name in LETRAS or name.isdigit()):
            self.token = (self.token + name)[-12:]
        elif name == "backspace":
            self.token = self.token[:-1]
        elif name in SEPARADORES or len(name) == 1:
            self.token = ""

    def feed(self, name, scan_code, event_type, now, campo=True, juego=False):
        """Devuelve el motivo (str) si parece gato, o None.
        juego=True (app en pantalla completa) relaja para no botar jugando."""
        c = self.cfg
        if event_type == "up":
            self.held.pop(scan_code, None)
            return None

        self.held.setdefault(scan_code, (name, now))
        # limpiar teclas fantasma (se perdio el key-up al cambiar de ventana)
        for sc, (nm, t) in list(self.held.items()):
            if now - t > 8.0:
                del self.held[sc]
        self.recent[scan_code] = (name, now)
        for sc, (nm, t) in list(self.recent.items()):
            if now - t > c["burst_window"]:
                del self.recent[sc]
        self._actualiza_token(name)

        # --- frenos de emergencia: certeza alta, se dispara de inmediato ---

        # 1) velocidad imposible para una mano humana
        if c["velocidad"]:
            self.downs.append(now)
            self.downs = [t for t in self.downs if now - t <= c["vel_window"]]
            if len(self.downs) >= c["vel_keys"] and not juego:
                return "tecleo imposible de rapido"

        # 2) la misma tecla machacada (aaaaaaa): antes contaba como una sola
        if c["repeticion"] and name not in EXENTAS_HOLD:
            if scan_code == self.rep_sc and now - self.rep_t0 <= c["rep_window"]:
                self.rep_n += 1
                if self.rep_n >= c["rep_keys"]:
                    return "misma tecla repetida"
            else:
                self.rep_sc, self.rep_n, self.rep_t0 = scan_code, 1, now

        # 3) basura acumulada aunque se escriba despacio (sdrtg, rz555).
        # Pide >=2 letras: asi escribir numeros sueltos (1234, x1000) no cuenta.
        if c["basura"] and c["prediccion"] and len(self.token) >= c["basura_min"]:
            if sum(ch in LETRAS for ch in self.token) >= 2 and self.lx.score(self.token) < 0.25:
                return "texto sin sentido"

        if c["simultaneas"]:
            # los modificadores no cuentan: Ctrl+Shift+X es un atajo, no un gato
            nomod = [nm for (nm, t) in self.held.values()
                     if now - t < 1.5 and nm not in MODIFICADORES]
            if len(nomod) >= c["held_threshold"]:
                if not (juego and all(k in GAMING for k in nomod)):
                    return "teclas simultaneas"

        if c["rafaga"]:
            nombres = [nm for (nm, t) in self.recent.values()]
            agresivo = c["sin_campo"] and not campo
            keys = c["burst_keys"] - 2 if agresivo else c["burst_keys"]
            if juego:
                keys += 2
            if len(self.recent) >= keys:
                if juego and all(k in GAMING for k in nombres):
                    return None  # estas jugando (WASD/flechas), no un gato
                # la prediccion solo aplica si de verdad se esta escribiendo texto:
                # una rafaga de F-keys/especiales no forma palabra y siempre es gato
                # escribir (letras o numeros) no es "especial"; F-keys y demas si
                normales = sum(1 for k in nombres
                               if len(k) == 1 and (k in LETRAS or k.isdigit()))
                if normales < len(nombres) / 2:
                    return "rafaga de teclas especiales"
                if not c["prediccion"] or agresivo:
                    return "rafaga sin sentido"
                # sin al menos 2 letras no hay texto que juzgar (numeros sueltos)
                if sum(ch in LETRAS for ch in self.token) < 2:
                    return None
                score = self.lx.score(self.token)
                # el texto ajusta las sospechas: una palabra (o principio de
                # palabra) valida y comun tolera mas rafaga; la basura pura
                # dispara antes
                if score >= 0.8:
                    keys += 2
                elif score < 0.25:
                    keys = max(3, keys - 1)
                if len(self.recent) >= keys and score < SCORE_THRESH:
                    return "rafaga sin palabra valida"
        return None

    def check_hold(self, now):
        """Se llama periodicamente: detecta una tecla pegada mucho tiempo."""
        if not self.cfg["tecla_pegada"]:
            return None
        limite = self.cfg["hold_ms"] / 1000.0
        for name, t in list(self.held.values()):
            if name not in EXENTAS_HOLD and now - t >= limite:
                return "tecla pegada"
        return None
