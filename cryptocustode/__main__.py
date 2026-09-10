"""`python -m cryptocustode`: l'unico comando di avvio dell'applicazione."""

from cryptocustode.api.app import PortaOccupata, avvia

if __name__ == "__main__":
    try:
        avvia()
    except PortaOccupata as errore:
        # Un messaggio, non una traccia di stack: chi usa questa app non legge
        # Python. `SystemExit` con del testo stampa su stderr ed esce con 1.
        raise SystemExit(f"CryptoCustode non si è avviato: {errore}")
