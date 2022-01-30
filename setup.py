from setuptools import setup, find_packages

setup(
    name="psyche",
    version="0.0.1",
    author="Matteo Cafasso",
    author_email="noxdafox@gmail.com",
    description=(""),
    license="",
    packages=find_packages(),
    install_requires=[
        'clipspy>=1.0.0',
        'lark>=1.0.0'
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "Topic :: Software Development :: Libraries :: Python Modules"
    ]
)
