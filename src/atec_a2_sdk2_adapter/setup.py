from glob import glob
from setuptools import find_packages, setup


PACKAGE_NAME = "atec_a2_sdk2_adapter"


setup(
    name=PACKAGE_NAME,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{PACKAGE_NAME}"]),
        (f"share/{PACKAGE_NAME}", ["package.xml", "README.md"]),
        (f"share/{PACKAGE_NAME}/config", glob("config/*.yaml")),
        (f"share/{PACKAGE_NAME}/launch", glob("launch/*.launch.py")),
    ],
    install_requires=["setuptools"],
    tests_require=["pytest"],
    zip_safe=True,
    maintainer="student",
    maintainer_email="student@example.com",
    description="Fail-closed ROS 2 adapter for the Unitree A2 SDK2 Sport service.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "a2_sdk2_adapter = atec_a2_sdk2_adapter.node:main",
        ],
    },
)
