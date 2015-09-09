import codecs
from setuptools import setup


with codecs.open('README.rst', encoding='utf-8') as f:
    long_description = f.read()

setup(
    name="dumputils",
    version="1.0.0",
    license='http://www.apache.org/licenses/LICENSE-2.0',
    description="Nothing",
    author='greatyao',
    author_email='greatyao@gmail.com',
    url='https://github.com/greatyao/dumputils',
    packages=['dumputils', 'dumputils.crypto'],
    package_data={
        'dumputils': ['README.rst', 'LICENSE']
    },
    install_requires=[],
    entry_points="""
    [console_scripts]
    dumpclient = dumputils.theclient:main
    """,
    classifiers=[
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: Implementation :: PyPy',
        'Topic :: Internet :: Proxy Servers',
    ],
    long_description=long_description,
)
