"""Category rules: known tricky cases found while drafting (Amendment 1, item 5)."""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "pipeline"))
from categorize import Categorizer  # noqa: E402

cat = Categorizer()

def test_arrange_is_not_range():
    t = "PROVIDE SUFFICIENT METAL RECEPTACLES FOR GARBAGE AND ARRANGE FOR COLLECTION"
    assert "appliance_other" not in cat.violation("571", t)

def test_self_closing_code_530_text_says_arrange():
    assert "self_closing_doors" in cat.violation("530", "ARRANGE AND MAKE SELF-CLOSING THE DOORS")

def test_gas_supply_is_outage_not_leak():
    s = cat.violation("742", "PROVIDE AN ADEQUATE SUPPLY OF GAS TO THE FIXTURES AT RANGE IN THE KITCHEN")
    assert "gas_outage" in s and "appliance_gas_leak" not in s and "appliance_other" not in s

def test_wired_glass_is_not_wiring():
    assert "electrical_wiring" not in cat.violation("502", "REPAIR THE BROKEN WIRED GLASS AT STAIR DOOR")

def test_exposed_bx_is_wiring():
    assert "electrical_wiring" in cat.violation("501", "EXPOSED BX CABLES AT DUMBWAITER RUNNING FROM CELLAR")

def test_smoke_detector_notice_is_not_detector():
    assert "smoke_detector" not in cat.violation("700", "POST A PROPER NOTICE OF SMOKE DETECTOR REQUIREMENTS AT MAIL BOX")
    assert "admin_paperwork" in cat.violation("700", "POST A PROPER NOTICE OF SMOKE DETECTOR REQUIREMENTS AT MAIL BOX")

def test_dumbwaiter_sign_marks_presence_only():
    t = "POST A SIGN INDICATING HOURS OF COLLECTION WHERE DUMBWAITER SERVICE IS NOT PROVIDED"
    s = cat.violation("1", t)
    assert "dumbwaiter" in s and "vertical_openings" not in s

def test_dumbwaiter_door_self_closing_is_three_categories():
    t = "REPLACE OR REPAIR THE SELF-CLOSING DOORS THAT IS MISSING OR DEFECTIVE LATCH AT DUMBWAITER DOOR"
    assert {"dumbwaiter", "vertical_openings", "self_closing_doors"} <= cat.violation("693", t)

def test_ac_blocking_fire_escape_is_egress():
    t = "ABATE THE NUISANCE CONSISTING OF AIR CONDITIONER UNIT INSTALLED AT FIRE ESCAPE WINDOW OBSTRUCTING EGRESS"
    assert "egress_obstruction" in cat.violation("510", t)

def test_complaints():
    assert "appliance_gas_leak" in cat.complaint("APPLIANCE", "ELECTRIC/GAS RANGE", "GAS SHUT-OFF VALVE LEAKING")
    assert "gas_outage" in cat.complaint("GENERAL", "COOKING GAS", "SHUT-OFF")
    assert "stove_controls" in cat.complaint("APPLIANCE", "ELECTRIC/GAS RANGE", "NO STOVE KNOB COVERS")
    assert cat.complaint("ELEVATOR", "MAINTENANCE", "DIRTY OR UNSANITARY") == set()

def test_radiator_and_faucet_knobs_are_not_stove_controls():
    assert "stove_controls" not in cat.violation("506", "REPLACE WITH NEW THE MISSING CONTROL KNOB ON THE RADIATOR")
    assert "stove_controls" not in cat.violation("579", "REPAIR THE LEAKY FAUCETS AT BATHTUB (CONTROL KNOB DISLOGGED)")
    assert "stove_controls" in cat.violation("506", "REPLACE WITH NEW THE MISSING STOVE KNOBS")
    assert "stove_controls" in cat.violation("504", "PROVIDE CHILD SAFETY KNOB COVERS AT RANGE")

def test_not_sparking_is_not_sparking():
    assert "electrical_sparking" not in cat.complaint("ELECTRIC", "WIRING", "EXPOSED, NOT SPARKING")
    assert "electrical_sparking" in cat.complaint("ELECTRIC", "WIRING", "EXPOSED AND SPARKING")
    assert "electrical_sparking" in cat.violation("501", "REPAIR THE DEFECTIVE ELECTRICAL OUTLETS (SPARKS)")

def test_outlet_child_covers_are_not_wiring():
    s = cat.violation("504", "PROVIDE CHILD SAFETY COVER AT ELECTRICAL OUTLET ON THE NORTH WALL")
    assert "electrical_wiring" not in s and "child_safety_covers" in s
    s = cat.violation("504", "PROVIDE 10 OUTLET SAFETY CAPS. 5 AT NORTH WALL")
    assert "electrical_wiring" not in s and "child_safety_covers" in s

def test_flickering_lights_stay_in_wiring():
    assert "electrical_wiring" in cat.complaint("ELECTRIC", "LIGHTING", "DIMS OR FLICKERS")
