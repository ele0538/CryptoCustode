"""Le soglie del verdetto di scansione (spec §12).

Stanno qui perché siano ritoccabili e testabili senza toccare la logica che le usa.
"""

# Sotto questa soglia una pagina si considera priva di testo utile.
CARATTERI_MINIMI_PAGINA = 40

# Frazione dell'area di pagina coperta da immagini oltre la quale la pagina
# si considera prevalentemente raster.
FRAZIONE_IMMAGINE_MASSIMA = 0.5
