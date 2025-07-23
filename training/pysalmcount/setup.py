from setuptools import setup, find_packages

setup(
    name='pysalmcount',
    version='0.1',
    packages=find_packages(),
    description='Motion Detection and Counter',
    author='Sami Ma',
    author_email='masamim@sfu.ca',
    # List of dependencies
    install_requires=[
        'numpy',
        'pandas',
        'requests'
    ],
)

