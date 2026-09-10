import pytest

from cryptocustode.core.errors import InvalidEncoding
from cryptocustode.core.ingest.txt_loader import carica_txt


def test_utf8_valido_viene_decodificato():
    assert carica_txt("Contratto firmato a Torino.".encode("utf-8")) == (
        "Contratto firmato a Torino."
    )


def test_accenti_e_simboli_sopravvivono():
    testo = "Società à è ì ò ù — € 1.200,00"
    assert carica_txt(testo.encode("utf-8")) == testo


def test_testo_vuoto_e_lecito():
    assert carica_txt(b"") == ""


def test_byte_non_utf8_solleva_invalid_encoding():
    # 0xE8 è "è" in latin-1: da solo non è una sequenza UTF-8 valida.
    with pytest.raises(InvalidEncoding):
        carica_txt("perch\xe8".encode("latin-1"))


def test_il_messaggio_cita_l_offset_del_byte():
    # "abc" occupa gli offset 0,1,2; il byte invalido sta all'offset 3.
    with pytest.raises(InvalidEncoding, match="3"):
        carica_txt(b"abc\xe8def")


def test_nessun_fallback_silenzioso_ad_altre_codifiche():
    # Con un fallback a latin-1 questa chiamata restituirebbe "perchè no"
    # invece di sollevare: è esattamente il comportamento che la spec vieta.
    with pytest.raises(InvalidEncoding):
        carica_txt("perch\xe8 no".encode("latin-1"))
