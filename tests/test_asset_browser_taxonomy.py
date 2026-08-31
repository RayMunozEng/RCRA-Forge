from ui.asset_browser import _classify_model_path


def test_visual_effect_source_wins_over_character_filename():
    assert _classify_model_path(
        "visualeffect/characters/hero/hero_robot_visor_scan.model"
    ) == ("Visual effects", None)


def test_cinematic_source_wins_over_enemy_filename():
    assert _classify_model_path(
        "cinematics/finale/exported/enm_emperor_mech.model"
    ) == ("Cinematics & UI", None)


def test_character_and_equipment_sources_remain_semantic():
    assert _classify_model_path(
        "characters/enemy/enm_grunthor/enm_grunthor.model"
    ) == ("Enemies", None)
    assert _classify_model_path(
        "equipment/weapon/wpn_burstpistol/wpn_burstpistol.model"
    ) == ("Weapons & gadgets", None)


def test_planet_path_maps_to_location():
    assert _classify_model_path(
        "environment/sargasso/architecture/sar_arch_wall.model"
    ) == ("Planets & locations", "Sargasso")
