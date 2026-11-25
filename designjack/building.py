"""Builds the clean base model: a small two-storey clinic in IFC4.

The model carries no geometry. The agent tools only read metadata
(names, types, property sets), which is exactly the surface an AI agent
connected to a design-data MCP server reads.
"""

from __future__ import annotations

import ifcopenshell
import ifcopenshell.api as api

PROJECT_NAME = "Riverside Clinic"
PROJECT_DESCRIPTION = "Schematic design model, issued for coordination."

# (storey, name, object_type, description, psets)
WALLS = [
    ("Level 1", "Wall-L1-N", "Exterior - CMU 300", "North exterior wall", {"Pset_WallCommon": {"FireRating": "60 min", "IsExternal": True}}),
    ("Level 1", "Wall-L1-S", "Exterior - CMU 300", "South exterior wall", {"Pset_WallCommon": {"FireRating": "60 min", "IsExternal": True}}),
    ("Level 1", "Wall-L1-E", "Exterior - CMU 300", "East exterior wall", {"Pset_WallCommon": {"FireRating": "60 min", "IsExternal": True}}),
    ("Level 1", "Wall-L1-W", "Exterior - CMU 300", "West exterior wall", {"Pset_WallCommon": {"FireRating": "60 min", "IsExternal": True}}),
    ("Level 2", "Wall-L2-N", "Exterior - Steel Stud 200", "North exterior wall", {"Pset_WallCommon": {"FireRating": "45 min", "IsExternal": True}}),
    ("Level 2", "Wall-L2-S", "Exterior - Steel Stud 200", "South exterior wall", {"Pset_WallCommon": {"FireRating": "45 min", "IsExternal": True}}),
    ("Level 2", "Wall-L2-Core", "Interior - Shaft 150", "Stair and elevator core", {"Pset_WallCommon": {"FireRating": "120 min", "IsExternal": False}}),
    ("Level 2", "Wall-L2-Corridor", "Interior - Partition 100", "Corridor partition", {"Pset_WallCommon": {"FireRating": "20 min", "IsExternal": False}}),
]

DOORS = [
    ("Level 1", "Door-101", "Single Swing 900", "Main entrance", {"Pset_DoorCommon": {"FireRating": "20 min", "IsExternal": True}}),
    ("Level 1", "Door-102", "Single Swing 900", "Reception to corridor", {"Pset_DoorCommon": {"FireRating": "20 min", "IsExternal": False}}),
    ("Level 1", "Door-103", "Double Swing 1800", "Stair 1", {"Pset_DoorCommon": {"FireRating": "90 min", "IsExternal": False}}),
    ("Level 2", "Door-201", "Single Swing 900", "Exam Room 3", {"Pset_DoorCommon": {"FireRating": "20 min", "IsExternal": False}}),
    ("Level 2", "Door-202", "Single Swing 900", "Exam Room 4", {"Pset_DoorCommon": {"FireRating": "20 min", "IsExternal": False}}),
    ("Level 2", "Door-203", "Double Swing 1800", "Stair 1", {"Pset_DoorCommon": {"FireRating": "90 min", "IsExternal": False}}),
]

WINDOWS = [
    ("Level 1", "Window-L1-01", "Fixed 1200x1500", "Reception glazing", {"Pset_WindowCommon": {"IsExternal": True}}),
    ("Level 1", "Window-L1-02", "Fixed 1200x1500", "Waiting room glazing", {"Pset_WindowCommon": {"IsExternal": True}}),
    ("Level 2", "Window-L2-01", "Casement 900x1200", "Exam Room 3", {"Pset_WindowCommon": {"IsExternal": True}}),
    ("Level 2", "Window-L2-02", "Casement 900x1200", "Exam Room 4", {"Pset_WindowCommon": {"IsExternal": True}}),
]

SPACES = [
    ("Level 1", "Reception", "Public", "Front desk and check-in", {"Qto_SpaceBaseQuantities": {"NetFloorArea": 42.0}}),
    ("Level 1", "Waiting Room", "Public", "Patient waiting", {"Qto_SpaceBaseQuantities": {"NetFloorArea": 65.5}}),
    ("Level 2", "Exam Room 3", "Clinical", "General exam", {"Qto_SpaceBaseQuantities": {"NetFloorArea": 14.2}}),
    ("Level 2", "Exam Room 4", "Clinical", "General exam", {"Qto_SpaceBaseQuantities": {"NetFloorArea": 14.8}}),
    ("Level 2", "Staff Lounge", "Staff", "Break room", {"Qto_SpaceBaseQuantities": {"NetFloorArea": 22.6}}),
]

ELEMENT_TABLE = {
    "IfcWall": WALLS,
    "IfcDoor": DOORS,
    "IfcWindow": WINDOWS,
    "IfcSpace": SPACES,
}


def build_base_model() -> ifcopenshell.file:
    """Return an in-memory IFC4 file for the clean clinic model."""
    f = api.run("project.create_file", version="IFC4")
    project = api.run("root.create_entity", f, ifc_class="IfcProject", name=PROJECT_NAME)
    project.Description = PROJECT_DESCRIPTION
    api.run("unit.assign_unit", f)

    site = api.run("root.create_entity", f, ifc_class="IfcSite", name="Riverside Site")
    api.run("aggregate.assign_object", f, relating_object=project, products=[site])
    building = api.run("root.create_entity", f, ifc_class="IfcBuilding", name="Clinic Building")
    api.run("aggregate.assign_object", f, relating_object=site, products=[building])

    storeys = {}
    for i, name in enumerate(["Level 1", "Level 2"]):
        st = api.run("root.create_entity", f, ifc_class="IfcBuildingStorey", name=name)
        st.Elevation = float(i * 4)
        api.run("aggregate.assign_object", f, relating_object=building, products=[st])
        storeys[name] = st

    for ifc_class, rows in ELEMENT_TABLE.items():
        for storey, name, object_type, description, psets in rows:
            el = api.run("root.create_entity", f, ifc_class=ifc_class, name=name)
            el.ObjectType = object_type
            el.Description = description
            if ifc_class == "IfcSpace":
                api.run("aggregate.assign_object", f, relating_object=storeys[storey], products=[el])
            else:
                api.run("spatial.assign_container", f, relating_structure=storeys[storey], products=[el])
            for pset_name, props in psets.items():
                is_qto = pset_name.startswith("Qto_")
                ps = api.run("pset.add_qto" if is_qto else "pset.add_pset", f, product=el, name=pset_name)
                api.run("pset.edit_qto" if is_qto else "pset.edit_pset", f,
                        **({"qto": ps} if is_qto else {"pset": ps}), properties=props)
    return f
