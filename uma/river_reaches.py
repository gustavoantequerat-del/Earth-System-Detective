"""Tramos del Desaguadero y del Mauri. Sin dependencias de Earth Engine para que el motor pueda importarlos."""

# tramos del cauce principal por km desde la salida del Titicaca (Uru Uru empieza cerca del km 330)
REACHES = [("T1", "Salida del Titicaca a Nazacara", 0, 60), ("T2", "Nazacara a Calacoto", 60, 115),
           ("T3", "Calacoto a Ulloma", 115, 210), ("T4", "Ulloma a Chuquina", 210, 300),
           ("T5", "Chuquina a Uru Uru", 300, 330), ("T6", "Uru Uru a Poopo", 345, 425)]
MAURI = ("M", "Rio Mauri (afluente desde Peru)")
FEEDS = {"uru_uru": ["T1", "T2", "T3", "T4", "T5", "M"], "poopo": ["T1", "T2", "T3", "T4", "T5", "T6", "M"]}
# agua medida en el rio que entra a cada laguna (tramo que no se superpone con la laguna). El Poopo usa la
# superficie del Titicaca: su tramo de entrada (T6) se mete dentro del lago y se explicaria a si mismo.
RIVER_INFLOW = {"uru_uru": ("T4", "al agua del Desaguadero antes de Uru Uru (tramo Ulloma-Chuquina)")}
