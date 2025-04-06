from setuptools import setup, find_packages

setup(
    name="madrona_gpudrive",
    version="0.1.0",
    packages=find_packages(include=["gpudrive"]),
    package_data={
        "madrona_gpudrive": ["cpython-31*-*.so"],
        "gpudrive"
    },
    include_package_data=True,
)
