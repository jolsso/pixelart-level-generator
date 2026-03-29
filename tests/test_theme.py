import pytest
from pixelart_map._theme import strip_theme_name


@pytest.mark.parametrize("folder,expected", [
    # Standard interior: _Singles_Shadowless_NNxNN suffix
    ("5_Classroom_and_Library_Singles_Shadowless_48x48", "Classroom_and_Library"),
    ("2_Living_Room_Singles_Shadowless_48x48",           "Living_Room"),
    ("4_Bedroom_Singles_Shadowless_48x48",               "Bedroom"),
    ("3_Bathroom_Singles_Shadowless_48x48",              "Bathroom"),
    ("8_Gym_Singles_Shadowless_48x48",                   "Gym"),
    ("7_Art_Singles_Shadowless_48x48",                   "Art"),
    ("14_Basement_Singles_Shadowless_48x48",             "Basement"),
    ("26_Condominium_Singles_Shadowless_48x48",          "Condominium"),
    # Interior with asset pack typo: SIngles (capital I)
    ("19_Hospital_SIngles_Shadowless_48x48",             "Hospital"),
    # Interior without "Singles": only _Shadowless_NNxNN suffix
    ("6_Music_and_Sport_Shadowless_48x48",               "Music_and_Sport"),
    # Standard exterior: _Singles_NNxNN suffix
    ("16_Office_Singles_16x16",                          "Office"),
    ("13_School_Singles_16x16",                          "School"),
    ("1_Terrains_and_Fences_Singles_16x16",              "Terrains_and_Fences"),
    ("9_Shopping_Center_and_Markets_Singles_16x16",      "Shopping_Center_and_Markets"),
    # Exterior with normalization: MIlitary typo
    ("23_MIlitary_Base_Singles_16x16",                   "Military_Base"),
    # Exterior singular names (not plural — matches actual asset pack)
    ("4_Generic_Building_Singles_16x16",                 "Generic_Building"),
    ("5_Floor_Modular_Building_Singles_16x16",           "Floor_Modular_Building"),
])
def test_strip_theme_name(folder, expected):
    assert strip_theme_name(folder) == expected
