import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="PlanetarySystemStacker-Rolf-Hempel", # Replace with your own username
    version="0.8.0",
    author="Rolf Hempel",
    author_email="rolf6419@gmx.de",
    description="PlanetarySystemStacker",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Rolf-Hempel/PlanetarySystemStacker",
    packages=setuptools.find_packages(),
    install_requires=[
        'mkl',
        'matplotlib',
        'psutil',
        'PyQt5',
        'scipy',
        'astropy',
        'scikit-image',
        'opencv-python'
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.5',
    entry_points={
        "console_scripts": [
        "PlanetarySystemStacker=PlanetarySystemStacker.planetary_system_stacker:main",
        ]
    },
)