from setuptools import setup

setup(
    name="wcf-binary parser",
    version="0.6.0",
    author="Timo Schmid",
    author_email="tschmid@ernw.de",
    description="A library for transforming wcf-binary data from and to xml",
    license="BSD",
    keywords="wcf wcf-binary xml",
    url="",
    packages=['wcf', 'wcf.records'],
    scripts=['wcf2xml.py', 'xml2wcf.py'],
    long_description="",
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Topic :: Utilities",
        "License :: OSI Approved :: BSD License",
        "Programming Language :: Python :: 3",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
