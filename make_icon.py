"""Genera gatoguard.ico (varios tamaños) con la carita de gato. Reproducible."""
from PIL import Image, ImageDraw

S = 256
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

azul = (58, 122, 254, 255)
oscuro = (16, 16, 20, 255)

# fondo redondeado azul
d.rounded_rectangle([8, 8, S - 8, S - 8], radius=56, fill=azul)

# orejas
d.polygon([(70, 96), (104, 40), (128, 96)], fill=oscuro)
d.polygon([(128, 96), (152, 40), (186, 96)], fill=oscuro)

# cara
d.ellipse([56, 88, 200, 216], fill=oscuro)

# ojos
d.ellipse([92, 132, 112, 160], fill=azul)
d.ellipse([144, 132, 164, 160], fill=azul)

# nariz + bigotes
d.polygon([(120, 168), (136, 168), (128, 180)], fill=azul)
for y in (170, 182):
    d.line([(60, y), (104, y - 4)], fill=azul, width=4)
    d.line([(152, y - 4), (196, y)], fill=azul, width=4)

tam = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
img.save("gatoguard.ico", sizes=tam)
print("gatoguard.ico generado")
