# 🐈 GatoGuard

[![Release](https://img.shields.io/github/v/release/leostriker111/GatoGuard)](https://github.com/leostriker111/GatoGuard/releases)
[![Descargas](https://img.shields.io/github/downloads/leostriker111/GatoGuard/total)](https://github.com/leostriker111/GatoGuard/releases)
[![Plataforma](https://img.shields.io/badge/plataforma-Windows-0078D6?logo=windows)](#)
[![Python](https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white)](#)
[![Licencia](https://img.shields.io/badge/licencia-PolyForm%20Noncommercial-ff69b4)](LICENSE)

Anti-gato para el teclado en **Windows**, al estilo [PawSense](https://www.bitboost.com/pawsense/) pero libre y en tu idioma.

Detecta cuando un gato se sube al teclado analizando **el comportamiento del tecleo** (sin cámara) y bloquea la entrada hasta que un humano lo desbloquea. También destraba el "modo raro" que dejan los gatos (modificadores atorados, Sticky Keys, etc.).

> Nació porque tengo dos gatos a los que les encanta pasearse sobre el teclado. No existía un clon open source de PawSense para Windows con detección por comportamiento, así que aquí está.

---

## ✨ Características

- **Detección por comportamiento** (sin cámara, sin IA pesada):
  - Ráfaga de teclas sin sentido
  - Varias teclas mantenidas a la vez (una pata aplasta varias)
  - Una tecla pegada mucho tiempo (gato sentado encima)
- **Predicción de texto** para no botar cuando *tú* escribes rápido: compara contra un diccionario de frecuencias, tolera *typos* y errores de dedo, y a mayor frecuencia de la palabra admite más velocidad.
- **Multi-idioma auto-detectado**: agarra los idiomas de tu teclado de Windows. Incluye diccionarios de español e inglés; otros (p. ej. japonés en *romaji*) los cubre una heurística de vocales.
- **Bloqueo total** con un hook de bajo nivel propio: bloquea de verdad F11, la tecla Windows, `Win+Ctrl+D` (escritorio nuevo) y demás combos que otras herramientas dejan pasar.
- **Consciente de la app al frente**: relaja la detección en juegos a pantalla completa e ignora las teclas típicas de juego (WASD, flechas). Lista de apps a ignorar configurable.
- **Reset del teclado** al desbloquear: suelta modificadores atorados, apaga CapsLock y desactiva Sticky/Filter/Toggle keys.
- **Congelar el mouse** con `Ctrl+Alt+M` (aviso en una esquina): el gato juega con el puntero, tú lo congelas cuando quieras.
- **Modo descanso**: `Ctrl+Alt+G` deja de detectar sin cerrar la app (🐈 *hay gatos cerca* ↔ 😴 *no hay gatos cerca*), con panel de estado en la esquina.
- **Atajos que funcionan aun bloqueado**: `Ctrl+Alt+U` desbloquea, `Ctrl+Alt+M` congela el mouse, `Ctrl+Alt+H` oculta el panel.
- **Ícono en la bandeja** con GUI de configuración (todo ajustable en vivo).
- No requiere permisos de administrador.

---

## 🚀 Instalación

### Opción A — Ejecutable (lo más fácil)
Descarga `GatoGuard.exe` de la sección [Releases](../../releases) y ábrelo. Aparece un gatito en la bandeja del sistema. Listo.

### Opción B — Con pip (desde el código)
```bash
git clone https://github.com/leostriker111/GatoGuard.git
cd GatoGuard
pip install .
gatoguard
```

### Opción C — Correr directo
```bash
pip install -r requirements.txt
python gatoguard.py
```

Para que arranque solo con Windows, crea un acceso directo a `GatoGuard.exe` (o a `pythonw gatoguard.py`) en:
```
%AppData%\Microsoft\Windows\Start Menu\Programs\Startup
```

---

## 🎮 Uso

| Acción | Cómo |
|---|---|
| Desbloquear | Clic en cualquier parte de la pantalla de bloqueo, o `Ctrl+Alt+U` |
| Modo descanso (dejar de detectar sin cerrar) | `Ctrl+Alt+G` — alterna entre 🐈 *Hay gatos cerca* y 😴 *No hay gatos cerca* |
| Congelar / descongelar mouse | `Ctrl+Alt+M` (el aviso vive en una esquina) |
| Ocultar / mostrar el panel de estado | `Ctrl+Alt+H` |

> Al suspender la PC, la librería de teclado pierde su hook. GatoGuard **se reinicia solo** al despertar (proceso nuevo = hooks nuevos). Si alguna vez no responde, **bandeja → "Reactivar detección"** hace el mismo reinicio manualmente.

El **panel de estado** (esquina inferior derecha) muestra si está vigilando o en descanso, el estado del mouse y cómo ocultarlo. Es *click-through* (no estorba los clics).
| Configurar | Clic derecho en el ícono → **Configuración** |
| Resetear teclado ya | Menú de la bandeja → **Resetear teclado ahora** |
| Salir | Menú de la bandeja → **Salir** |

La configuración se guarda en `config.json` (junto al script, o en `%AppData%\GatoGuard\` si usas el `.exe`).

### Ajustar sensibilidad
Si te bota al escribir normal, abre **Configuración** y sube *Teclas en ráfaga* o *Teclas simultáneas*, o apaga la señal que te moleste. Si no detecta al gato lo suficientemente rápido, bájalas.

---

## 🧠 Cómo funciona

Un *hook* global de teclado alimenta un detector con cada evento. Se dispara si:

1. **simultáneas** — ≥ N teclas presionadas dentro de 1.5 s y aún sostenidas;
2. **ráfaga** — ≥ K teclas distintas en una ventana corta **y** lo tecleado no parece una palabra real (predicción de texto);
3. **tecla pegada** — una tecla (que no sea espacio/backspace/flechas/modificador) sostenida más de X ms.

Al dispararse, se instala un *hook* supresor (`keyboard.hook(..., suppress=True)`) que bloquea todo el teclado excepto el atajo de desbloqueo, y se muestra un overlay a pantalla completa.

## 📦 Estructura

| Archivo | Qué hace |
|---|---|
| `gatoguard.py` | App: hooks, bandeja, GUI, overlay |
| `deteccion.py` | Lógica pura de detección + predicción de texto |
| `winutils.py` | Helpers de Windows (campo de texto, reset, idiomas) |
| `test_deteccion.py` | Pruebas de la lógica |
| `es_50k.txt`, `en_50k.txt` | Diccionarios de frecuencias ([FrequencyWords](https://github.com/hermitdave/FrequencyWords)) |

## 🛠️ Construir el ejecutable
```powershell
pip install pyinstaller
./build.ps1
```
El `.exe` queda en `dist/GatoGuard.exe`.

## 🩷 Apoya el proyecto
GatoGuard es **gratis** y siempre lo será. Si te ahorró un desastre en el teclado, puedes invitarme un café — cada peso ayuda a que le siga metiendo features. Los donantes aparecen en los créditos. ¡Gracias! 🐈
<!-- Botón de Sponsor arriba a la derecha del repo, o Ko-fi (por configurar). -->

## 📝 Licencia
**[PolyForm Noncommercial 1.0.0](LICENSE)** — puedes usar, estudiar, modificar y compartir el software libremente **para fines no comerciales**. No se permite venderlo ni usarlo con fines de lucro. Diccionarios de [FrequencyWords](https://github.com/hermitdave/FrequencyWords) (MIT).
