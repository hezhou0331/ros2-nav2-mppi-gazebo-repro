#!/usr/bin/python3
"""Generate simulation-ready component URDFs from pristine vendor files."""

from pathlib import Path
import xml.etree.ElementTree as ET


PACKAGE = "atec_a2_p7_description"
ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "urdf" / "vendor"
COMPONENTS = ROOT / "urdf" / "components"


def write(tree: ET.ElementTree, path: Path) -> None:
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)


def add_primitive_collision(link: ET.Element, geometry: str, size: str,
                            xyz: str = "0 0 0", rpy: str = "0 0 0") -> None:
    collision = ET.SubElement(link, "collision")
    ET.SubElement(collision, "origin", {"xyz": xyz, "rpy": rpy})
    geometry_element = ET.SubElement(collision, "geometry")
    shape = ET.SubElement(geometry_element, geometry)
    if geometry == "box":
        shape.set("size", size)
    elif geometry == "cylinder":
        radius, length = size.split()
        shape.set("radius", radius)
        shape.set("length", length)
    elif geometry == "sphere":
        shape.set("radius", size)


def generate_a2() -> None:
    tree = ET.parse(VENDOR / "a2.urdf")
    root = tree.getroot()
    root.set("name", "unitree_a2_component")
    root.insert(0, ET.Comment(
        "Generated from the pinned Unitree A2 URDF; see docs/MODEL_PROVENANCE.md."
    ))
    for mesh in root.findall(".//mesh"):
        filename = Path(mesh.get("filename", "")).name
        mesh.set("filename", f"package://{PACKAGE}/meshes/a2/{filename}")
    write(tree, COMPONENTS / "a2.urdf.xacro")


def generate_p7() -> None:
    tree = ET.parse(VENDOR / "p7_arm_v3_umi_gripper_v3.urdf")
    root = tree.getroot()
    root.set("name", "p7_arm_v3_umi_gripper_v3_component")
    root.insert(0, ET.Comment(
        "Generated from the team-supplied P7 v3 model; passive UMI joints are locked."
    ))

    link_map = {
        link.get("name"): f"p7_{link.get('name')}" for link in root.findall("link")
    }
    joint_map = {
        joint.get("name"): f"p7_{joint.get('name')}" for joint in root.findall("joint")
    }
    for link in root.findall("link"):
        link.set("name", link_map[link.get("name")])
    for joint in root.findall("joint"):
        original_name = joint.get("name")
        joint.set("name", joint_map[original_name])
        parent = joint.find("parent")
        child = joint.find("child")
        if parent is not None:
            parent.set("link", link_map[parent.get("link")])
        if child is not None:
            child.set("link", link_map[child.get("link")])
        mimic = joint.find("mimic")
        if mimic is not None:
            mimic.set("joint", joint_map[mimic.get("joint")])

        # The supplied UMI linkage has no mimic equations. Keep it rigid in
        # navigation simulation and expose only the jaw-width prismatic joint.
        if original_name.startswith("umi_") and joint.get("type") == "continuous":
            joint.set("type", "fixed")
            for tag in ("axis", "limit", "dynamics"):
                element = joint.find(tag)
                if element is not None:
                    joint.remove(element)
        if original_name == "umi_clawj":
            limit = joint.find("limit")
            limit.set("effort", "20")
            limit.set("velocity", "0.10")

    for mesh in root.findall(".//mesh"):
        source = mesh.get("filename", "")
        if "/p7_v3/" in source:
            mesh.set("filename", f"package://{PACKAGE}/meshes/p7/{Path(source).name}")
        else:
            mesh.set(
                "filename",
                f"package://{PACKAGE}/meshes/umi_gripper_v3/{Path(source).name}",
            )

    # Detailed meshes remain visual. Primitive collisions keep Gazebo usable.
    for link in root.findall("link"):
        for collision in list(link.findall("collision")):
            link.remove(collision)
    collisions = {
        "p7_base_link": ("cylinder", "0.055 0.13", "0 0 0.065", "0 0 0"),
        "p7_link1": ("cylinder", "0.055 0.12", "0 0 0", "0 0 0"),
        "p7_link2": ("cylinder", "0.043 0.24", "0 -0.12 0", "1.5708 0 0"),
        "p7_link3": ("cylinder", "0.040 0.20", "0 0 -0.10", "0 0 0"),
        "p7_link4": ("cylinder", "0.045 0.31", "0 -0.155 0", "1.5708 0 0"),
        "p7_link5": ("cylinder", "0.038 0.20", "0 0 -0.10", "0 0 0"),
        "p7_link6": ("sphere", "0.055", "0 0 0", "0 0 0"),
        "p7_link7": ("box", "0.10 0.07 0.07", "-0.035 0 0", "0 0 0"),
        "p7_tool": ("cylinder", "0.030 0.09", "-0.045 0 0", "0 1.5708 0"),
        "p7_umi_base_link": ("box", "0.12 0.10 0.07", "0.055 0 0", "0 0 0"),
        "p7_umi_claw": ("box", "0.09 0.08 0.035", "-0.01 0 0", "0 0 0"),
    }
    links = {link.get("name"): link for link in root.findall("link")}
    for name, (geometry, size, xyz, rpy) in collisions.items():
        add_primitive_collision(links[name], geometry, size, xyz, rpy)

    write(tree, COMPONENTS / "p7_arm_v3_umi_gripper_v3.urdf.xacro")


if __name__ == "__main__":
    COMPONENTS.mkdir(parents=True, exist_ok=True)
    generate_a2()
    generate_p7()
